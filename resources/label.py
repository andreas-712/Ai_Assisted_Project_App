'''
----------------------------
Label actions (and AI context creation indirectly)
USER INTERACTIONS
----------------------------
'''

from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy.exc import SQLAlchemyError, IntegrityError

from db import db
from models import ProjectModel, LabelModel, RefinedLabelModel
from schemas import ProjectAddLabelsSchema, LabelSchema, RefinedLabelUpdateSchema, RefinedLabelSchema, LabelDecisionArgs

from resources.gemini import gemini_service_instance

blp = Blueprint("labels", __name__, description = "Operations on project labels")

MAX_LABELS = 10

@blp.route("/projects/<int:project_id>/labels")
class ProjectLabelsList(MethodView):
    @jwt_required()
    @blp.response(200, LabelSchema(many = True))
    # Return all input labels that user has entered for a project
    def get(self, project_id):
        # Initialize user and retrieve ID
        current_user_id = get_jwt_identity()

        # Find project by ID
        project = ProjectModel.query.filter_by(id = project_id, user_id = current_user_id).first_or_404(
            description = "Project not found or you do not have permission to access its labels."
        )

        return project.labels.all()
    
    @jwt_required()
    @blp.arguments(ProjectAddLabelsSchema)
    @blp.response(201, LabelSchema(many = True))
    def post(self, labels_data, project_id):
        # Find user
        current_user_id = get_jwt_identity()
        # Verify user
        project = ProjectModel.query.filter_by(id = project_id, user_id = current_user_id).first_or_404(
            description = "Project not found, or you do not have permission to add labels"
        )

        # Add 1-10 input labels
        if (project.labels.count() + len(labels_data["labels"])) >= MAX_LABELS:
            abort(400, message = f"Adding these labels would exceed limit of labels {MAX_LABELS} per project")

        created = []
        for label_text in labels_data["labels"]:
            new_label = LabelModel(text=label_text, project_id=project.id)
            db.session.add(new_label)
            created.append(new_label)

        db.session.commit()
        return created
    
# Actions on specific labels
@blp.route("/labels/<int:label_id>")
class LabelResource(MethodView):
    
    @jwt_required()
    @blp.arguments(LabelDecisionArgs)
    @blp.response(200, RefinedLabelSchema(many = True))
    def post(self, label_gen_data, label_id):
        # If "Yes", generate, otherwise descriptions will not be generated with AI
        # Default to no if decision not given
        label_gen_data = label_gen_data or {}
        gen_data = label_gen_data.get("user_decision", "No")

        current_user_id = get_jwt_identity()

        # Verify ownership of label through project
        label = (
            db.session.query(LabelModel)
            .join(ProjectModel, LabelModel.project_id == ProjectModel.id)
            .filter(
                LabelModel.id == label_id,
                ProjectModel.user_id == current_user_id
            )
            .first_or_404(description = "Label not found or access denied")
        )

        # If user didn’t select "Yes", skip generation
        if gen_data != "Yes":
            return RefinedLabelModel.query.filter_by(input_label_id=label.id).all()

        difficulties = ["simple", "intermediate", "in_depth"]

        try:
            results = []
            for difficulty in difficulties:
                refined = RefinedLabelModel.query.filter_by(
                    input_label_id=label.id, difficulty=difficulty
                ).first()

                refined_text_content = gemini_service_instance.refine_label_text(
                    label_text=label.text,
                    difficulty=difficulty,
                    project_name=label.project.name if label.project else None,
                    project_description=label.project.description if label.project else None,
                )

                if refined:
                    refined.generated_text = refined_text_content
                else:
                    refined = RefinedLabelModel(
                        generated_text=refined_text_content,
                        difficulty=difficulty,
                        input_label_id=label.id
                    )
                    db.session.add(refined)

                results.append(refined)

            db.session.commit()
            return results


        # Catch errors from Gemini
        except ConnectionError as e_gemini:
            db.session.rollback()
            abort(502, message=f"Error generating for label {label.text}: {str(e_gemini)}")
        except IntegrityError:
            db.session.rollback()
            abort(400, message="Database integrity error while saving refined labels")
        except SQLAlchemyError:
            db.session.rollback()
            abort(500, message="Database error while saving refined labels")
        except Exception as e:
            db.session.rollback()
            abort(500, message=f"Unexpected error: {e}")


    @jwt_required()
    @blp.response(200, LabelSchema)
    def get(self, label_id):
        # Find linked labels by user ID
        current_user_id = get_jwt_identity()
        # Ensure the label exists and belongs to a project owned by the current user
        label = db.session.query(LabelModel).join(ProjectModel).filter(
            LabelModel.id == label_id,
            ProjectModel.user_id == current_user_id
        ).first_or_404(description = "Label not found or access denied")

        return label

    @jwt_required()
    def delete(self, label_id):
        # Delete a specific label (and its associated refined_label)
        current_user_id = get_jwt_identity()
        # Ensure the label exists to a project and its user
        label = db.session.query(LabelModel).join(ProjectModel).filter(
            LabelModel.id == label_id,
            ProjectModel.user_id == current_user_id
        ).first_or_404(description = "Label not found or access denied")

        try:
            # Also deletes refined_label model due to cascade
            db.session.delete(label) 
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            abort(500, message = f"An error occurred while deleting the label")
                    
        return {"message": "Label deleted successfully"}
    

# For users to give short feedback, or to edit manually
# Must only have either feedback OR edits in a single request
@blp.route("/refined_labels/<int:refined_id>")
class RefinedLabelResource(MethodView):
    
    @jwt_required()
    @blp.arguments(RefinedLabelUpdateSchema)
    @blp.response(200, RefinedLabelSchema)
    def patch(self, update_data, refined_id):
        if not update_data:
            abort(400, message = "No data provided")

        current_user_id = get_jwt_identity()

        refined = (
            db.session.query(RefinedLabelModel)
            .join(LabelModel)
            .join(ProjectModel)
            .filter(
                RefinedLabelModel.id == refined_id,
                ProjectModel.user_id == current_user_id
            )
            .first_or_404(
                description = "Not found or access denied."
            )
        )

        has_feedback = "feedback" in update_data
        has_text = "generated_text" in update_data

        if not has_feedback and not has_text:
            abort(400, message = "Provide feedback or generated_text")

        if has_feedback and has_text:
            abort(400, message = "Cannot provide both feedback and generated_text in the same request")

        # Have user edit the text
        if has_text:
            refined.generated_text = update_data["generated_text"]

        # Have Gemini reconstruct the text
        elif has_feedback:
            try:
                new_text = gemini_service_instance.reconstruct_label_text(
                    old_output = refined.generated_text,
                    user_feedback = update_data["feedback"],
                    label_text = refined.input_label.text,
                    difficulty = refined.difficulty
                )
                refined.generated_text = new_text
            except ConnectionError as e:
                abort(502, message=str(e))

            # Overwrite the exisiting row in database

        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            abort(400, message = "Database integrity error updating label context")
        except SQLAlchemyError:
            db.session.rollback()
            abort(500, message = "Database error updating label context")

        return refined
