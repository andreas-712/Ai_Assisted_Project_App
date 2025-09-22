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
from schemas import ProjectAddLabelsSchema, LabelSchema, RefinedLabelUpdateSchema, RefinedLabelSchema, LabelGenerateArgs, LabelManualArgs

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
    
# *** Actions on specific labels ***

# Generate AI text, single difficulty (chosen)
@blp.route("/labels/<int:label_id>/generate")
class LabelGenerateResource(MethodView):
    
    @jwt_required()
    @blp.arguments(LabelGenerateArgs)
    @blp.response(200, RefinedLabelSchema)
    def post(self, label_gen_data, label_id):
        input_difficulty = label_gen_data["input_difficulty"]

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

        difficulties = {"simple", "intermediate", "in_depth"}

        # If backend makes mistake
        if input_difficulty not in difficulties:
            abort(400, message = "Error, please enter a valid difficulty (one of simple, intermediate, in_depth)")


        # *** Generating the text ***
        try:
            refined = RefinedLabelModel.query.filter_by(
                input_label_id=label.id, difficulty=input_difficulty
            ).first()

            refined_text_content = gemini_service_instance.refine_label_text(
                label_text=label.text,
                difficulty=input_difficulty,
                project_name=label.project.name if label.project else None,
                project_description=label.project.description if label.project else None,
                )

            if refined:
                refined.generated_text = refined_text_content
            else:
                refined = RefinedLabelModel(
                generated_text=refined_text_content,
                difficulty=input_difficulty,
                input_label_id=label.id
                )

            db.session.add(refined)
            db.session.commit()
            return refined

        # Catch errors from Gemini
        except ConnectionError as e_gemini:
            db.session.rollback()
            abort(502, message=f"Error generating for label {label.text}: {str(e_gemini)}")
        except IntegrityError:
            db.session.rollback()
            abort(400, message="Database integrity error while saving label description")
        except SQLAlchemyError:
            db.session.rollback()
            abort(500, message="Database error while saving label description")
        except Exception as e:
            db.session.rollback()
            abort(500, message=f"Unexpected error: {e}")


# Gets the label contents of a specific label ID
@blp.route("/labels/<int:label_id>")
class LabelResource(MethodView):
    @blp.response(200, LabelSchema)
    def get(self, label_id):
        label = (
            LabelModel.query
            .get_or_404(label_id)
        )
        return label


# For manually typing label descriptions
@blp.route("/labels/<int:label_id>/manual")
class LabelManualResource(MethodView):
    
    @jwt_required()
    @blp.arguments(LabelManualArgs)
    @blp.response(200, RefinedLabelSchema)
    def post(self, text_data, label_id):
        
        # Fields (difficulty and text)
        # Default to "simple" if difficulty not selected
        input_difficulty = text_data["input_difficulty"]
        input_text = text_data["input_text"].strip()

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

        difficulties = {"simple", "intermediate", "in_depth"}

        # If backend makes mistake
        if input_difficulty not in difficulties:
            abort(400, message = "Error, please enter a valid difficulty (one of simple, intermediate, in_depth)")

        if len(input_text) < 5:
            abort(400, message = "Error, please enter a label description longer than 5 characters")

        try:
            label_desc = RefinedLabelModel.query.filter_by(
                input_label_id=label.id, difficulty=input_difficulty
            ).first()

            if label_desc:
                label_desc.generated_text = input_text
            else:
                label_desc = RefinedLabelModel(
                    generated_text=input_text,
                    difficulty=input_difficulty,
                    input_label_id=label.id
                )

            db.session.add(label_desc)
            db.session.commit()
            return label_desc
        
        except IntegrityError:
            db.session.rollback()
            abort(400, message="Database integrity error while saving label description")
        except SQLAlchemyError:
            db.session.rollback()
            abort(500, message="Database error while saving label description")
        except Exception as e:
            db.session.rollback()
            abort(500, message=f"Unexpected error: {e}")


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
    
    @blp.response(200, RefinedLabelSchema)
    def get(self, refined_id):
        refined_label = (
            db.session.query(RefinedLabelModel)
            .join(RefinedLabelModel.input_label)  # keep if you need eager fields; not for auth
            .filter(RefinedLabelModel.id == refined_id)
            .first_or_404(description="Refined label not found")
        )
        return refined_label
    

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
