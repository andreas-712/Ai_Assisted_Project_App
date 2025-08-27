from marshmallow import Schema, fields, validate

# --- Plain Schemas: Core attributes, for basic input / ID assignments ---

# User registration and login
class PlainUserSchema(Schema):
    id = fields.Int(dump_only = True)
    username = fields.Str(required = True, validate=validate.Length(min=3, max=80))
    # Password is load_only, so it's never dumped.
    password = fields.Str(required = True, load_only = True, validate=validate.Length(min=8, max=256))

# User input labels
class PlainLabelSchema(Schema):
    id = fields.Int(dump_only = True)
    # Label name / text
    text = fields.Str(required = True, validate=validate.Length(min=1, max=100))

# For Gemini-generated outputs
class PlainRefinedLabelSchema(Schema):
    # Gemini-generated response to labels
    id = fields.Int(dump_only = True)
    generated_text = fields.Str(dump_only = True)
    # All labels present, but not necessarily displayed on dump (for quick access)
    difficulty = fields.Str(dump_only = True) 

# For user-inputed project images
class PlainImageSchema(Schema):
    id = fields.Int(dump_only = True)
    filename = fields.Str(dump_only = True)
    # Google Cloud Storage path
    gcs_path = fields.Str(dump_only = True)
    # Type of image (JPEG in this case)
    content_type = fields.Str(dump_only = True)

# Project creation
class PlainProjectSchema(Schema):
    id = fields.Int(dump_only = True)
    name = fields.Str(required = True, validate=validate.Length(min=1, max=120))
    description = fields.Str(required = True, validate=validate.Length(max=5000)) 

# Full Schemas: Inherits from Plain, but adds class inter-relationships

class ImageSchema(PlainImageSchema):
    projects = fields.Nested(PlainProjectSchema(), dump_only = True)

# Link projects to a user's account
class UserSchema(PlainUserSchema):
    projects = fields.List(fields.Nested(PlainProjectSchema()), dump_only=True)


class LabelSchema(PlainLabelSchema):
    # Pass ID from Project client
    project_id = fields.Int(required = True, load_only = True) 
     # To show which project a label belongs to
    project = fields.Nested(PlainProjectSchema(), dump_only = True)
    # Refined label 1-1 relation, can show its refined label
    refinements = fields.List(fields.Nested(PlainRefinedLabelSchema(), dump_only = True))
    # For user decision whether they want generated label descriptions
    user_decision = fields.Str(load_only = True)

# We don't want to link outputs directly to a project
# The link to the project is through the input label
class RefinedLabelSchema(PlainRefinedLabelSchema):
    # Related input_label, can show which input label it refines
    input_label = fields.Nested(PlainLabelSchema(), dump_only = True)


class ProjectSchema(PlainProjectSchema):
    user = fields.Nested(PlainUserSchema(), dump_only = True)
    labels = fields.List(fields.Nested(LabelSchema()), dump_only = True)
    images = fields.List(fields.Nested(PlainImageSchema()), dump_only = True)

# --- Schemas for Specific Operations (like updates or specialized inputs) ---

# Schema for updating a project
class ProjectUpdateSchema(Schema):
    name = fields.Str(validate = validate.Length(min = 1, max = 120))
    description = fields.Str(allow_none = True, validate = validate.Length(max = 5000))

# Schema to add multiple labels
class ProjectAddLabelsSchema(Schema):
    labels = fields.List(
        fields.Str(required = True, validate = validate.Length(min = 1, max = 100)),
        required = True,
        # Max 10 labels
        validate = validate.Length(min = 1, max = 10)
    )

class RefinedLabelCreateSchema(Schema):
    generated_text = fields.Str(allow_none = True)
    difficulty = fields.Str(required = True, validate=validate.OneOf(["simple", "intermediate", "in_depth"]))
    input_label_id = fields.Int(required = True, load_only = True)


# Schema for editing Gemini repsonse or giving feedback
class RefinedLabelUpdateSchema(Schema):
    feedback = fields.Str(required = True, load_only = True, validate = validate.Length(min = 5, max = 500))
    generated_text = fields.Str(validate = validate.Length(min = 3, max = 5000))
