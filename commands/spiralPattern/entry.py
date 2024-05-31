import adsk.core
import os

import adsk.fusion
from ...lib import fusionAddInUtils as futil
from ... import config

app = adsk.core.Application.get()
ui = app.userInterface


# Specify the command identity information.
CMD_ID = f"{config.COMPANY_NAME}_{config.ADDIN_NAME}_spiralPatternDialog"
CMD_NAME = "Spiral Pattern"
CMD_DESCRIPTION = "Pattern a component by translation and rotation along an axis"

# Specify that the command will be promoted to the panel.
IS_PROMOTED = False

# Define the location where the command button will be created.
# This is done by specifying the workspace, the tab, and the panel, and the
# command it will be inserted beside. Not providing the command to position it
# will insert it at the end.
WORKSPACE_ID = "FusionSolidEnvironment"
PANEL_ID = "SolidCreatePanel"
COMMAND_BESIDE_ID = "PatternDropDown"

# Resource location for command icons, here we assume a sub folder in this directory named "resources".
ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "")

# Local list of event handlers used to maintain a reference so
# they are not released and garbage collected.
local_handlers = []


# Executed when add-in is run.
def start():
    # Create a command Definition.
    cmd_def = ui.commandDefinitions.addButtonDefinition(
        CMD_ID, CMD_NAME, CMD_DESCRIPTION, ICON_FOLDER
    )
    cmd_def.toolClipFilename = os.path.join(ICON_FOLDER, "screenshot.png")

    # Define an event handler for the command created event. It will be called when the button is clicked.
    futil.add_handler(cmd_def.commandCreated, command_created)

    # ******** Add a button into the UI so the user can run the command. ********
    # Get the target workspace the button will be created in.
    workspace = ui.workspaces.itemById(WORKSPACE_ID)

    # Get the panel the button will be created in.
    panel = workspace.toolbarPanels.itemById(PANEL_ID)

    # Create the button command control in the UI after the specified existing command.
    control = panel.controls.addCommand(cmd_def, COMMAND_BESIDE_ID, False)

    # Specify if the command is promoted to the main toolbar.
    control.isPromoted = IS_PROMOTED


# Executed when add-in is stopped.
def stop():
    # Get the various UI elements for this command
    workspace = ui.workspaces.itemById(WORKSPACE_ID)
    panel = workspace.toolbarPanels.itemById(PANEL_ID)
    command_control = panel.controls.itemById(CMD_ID)
    cmd_def = ui.commandDefinitions.itemById(CMD_ID)

    # Delete the button command control
    if command_control:
        command_control.deleteMe()

    # Delete the command definition
    if cmd_def:
        cmd_def.deleteMe()


# Function that is called when a user clicks the corresponding button in the UI.
# This defines the contents of the command dialog and connects to the command related events.
def command_created(args: adsk.core.CommandCreatedEventArgs):
    # General logging for debug.
    futil.log(f"{CMD_NAME} Command Created Event")
    inputs = args.command.commandInputs

    # Create a selection input for the pattern occurrences
    occs_input = inputs.addSelectionInput("occs", "Objects", "Select pattern objects")
    occs_input.setSelectionLimits(1)
    occs_input.addSelectionFilter("Occurrences")

    # Create a selection input for the pattern axis
    direction_input = inputs.addSelectionInput(
        "direction", "Direction", "Select pattern direction"
    )
    direction_input.setSelectionLimits(1, 1)
    direction_input.addSelectionFilter("ConstructionLines")

    # Create a selection input for the pattern rotation origin point
    origin_input = inputs.addSelectionInput("origin", "Origin", "Rotation origin")
    origin_input.setSelectionLimits(1, 1)
    origin_input.addSelectionFilter("ConstructionPoints")

    # Create dropdown input for the pattern distribution
    distribution_input = inputs.addDropDownCommandInput(
        "distribution",
        "Distribution",
        adsk.core.DropDownStyles.LabeledIconDropDownStyle,
    )
    distribution_items = distribution_input.listItems
    distribution_items.add(
        "Spacing",
        True,
        os.path.join(ICON_FOLDER, "pattern", "distanceType", "spacing"),
    )
    distribution_items.add(
        "Extent",
        False,
        os.path.join(ICON_FOLDER, "pattern", "distanceType", "extent"),
    )
    distribution_input.isVisible = False

    # Create value input fot the pattern quantity
    quantity_input = inputs.addIntegerSpinnerCommandInput(
        "quantity", "Quantity", 2, 100, 1, 3
    )
    quantity_input.isVisible = False

    # Create distance value input for the pattern distance
    distance_input = inputs.addDistanceValueCommandInput(
        "distance", "Distance", adsk.core.ValueInput.createByReal(0)
    )
    distance_input.hasMinimumValue = False
    distance_input.hasMaximumValue = False
    distance_input.isVisible = False

    # Create angle value input for the pattern rotation
    angle_input = inputs.addAngleValueCommandInput(
        "angle",
        "Angle",
        adsk.core.ValueInput.createByReal(0),
    )
    angle_input.hasMinimumValue = False
    angle_input.hasMaximumValue = False
    angle_input.isVisible = False

    # Create checkbox input to define if the components copies should be new or not
    inputs.addBoolValueInput("isNewCopy", "Create Copy", True, "", False)

    # Connect to the events that are needed by this command.
    futil.add_handler(
        args.command.execute, command_execute, local_handlers=local_handlers
    )
    futil.add_handler(
        args.command.inputChanged, command_input_changed, local_handlers=local_handlers
    )
    futil.add_handler(
        args.command.executePreview, command_preview, local_handlers=local_handlers
    )
    futil.add_handler(
        args.command.validateInputs,
        command_validate_input,
        local_handlers=local_handlers,
    )
    futil.add_handler(
        args.command.destroy, command_destroy, local_handlers=local_handlers
    )


# This event handler is called when the user clicks the OK button in the command dialog or
# is immediately called after the created event not command inputs were created for the dialog.
def command_execute(args: adsk.core.CommandEventArgs):
    # General logging for debug.
    futil.log(f"{CMD_NAME} Command Execute Event")

    product = app.activeProduct

    if not isinstance(product, adsk.fusion.Design):
        raise ValueError("This command is only available within a Fusion design.")

    design = adsk.fusion.Design.cast(product)

    # Get the timeline index and the start position
    timeline = design.timeline
    timeline_start_position = timeline.markerPosition

    calculate_pattern(args.command.commandInputs)

    # Capture the end position of the design
    design.snapshots.add()

    # Get the timeline index and the end position
    timeline_end_position = timeline.markerPosition

    # Create a timeline group for the command features
    timeline_group = timeline.timelineGroups.add(
        timeline_start_position, timeline_end_position - 1
    )
    timeline_group.name = f"{CMD_NAME}"


# This event handler is called when the command needs to compute a new preview in the graphics window.
def command_preview(args: adsk.core.CommandEventArgs):
    # General logging for debug.
    futil.log(f"{CMD_NAME} Command Preview Event")

    calculate_pattern(args.command.commandInputs)


# This event handler is called when the user changes anything in the command dialog
# allowing you to modify values of other inputs based on that change.
def command_input_changed(args: adsk.core.InputChangedEventArgs):
    changed_input = args.input
    inputs = args.inputs

    # General logging for debug.
    futil.log(
        f"{CMD_NAME} Input Changed Event fired from a change to {changed_input.id}"
    )

    occs_input = adsk.core.SelectionCommandInput.cast(inputs.itemById("occs"))
    direction_input = adsk.core.SelectionCommandInput.cast(inputs.itemById("direction"))
    origin_input = adsk.core.SelectionCommandInput.cast(inputs.itemById("origin"))
    distribution_input = adsk.core.DropDownCommandInput.cast(
        inputs.itemById("distribution")
    )
    quantity_input = adsk.core.IntegerSpinnerCommandInput.cast(
        inputs.itemById("quantity")
    )
    distance_input = adsk.core.DistanceValueCommandInput.cast(
        inputs.itemById("distance")
    )
    angle_input = adsk.core.AngleValueCommandInput.cast(inputs.itemById("angle"))

    origin_point = adsk.core.Point3D.create(0, 0, 0)
    direction_vector = adsk.core.Vector3D.create(0, 0, 1)

    if origin_input.selectionCount > 0:
        origin_point = adsk.fusion.ConstructionPoint.cast(
            origin_input.selection(0).entity
        ).geometry

    if direction_input.selectionCount > 0:
        direction_vector = adsk.fusion.ConstructionAxis.cast(
            direction_input.selection(0).entity
        ).geometry.direction

    arbitrary_vector = adsk.core.Vector3D.create(
        direction_vector.z, direction_vector.x, direction_vector.y
    )
    if direction_vector.isParallelTo(arbitrary_vector):
        arbitrary_vector = adsk.core.Vector3D.create(
            -direction_vector.x, direction_vector.y, direction_vector.z
        )

    perp1_vector = direction_vector.crossProduct(arbitrary_vector)
    perp2_vector = direction_vector.crossProduct(perp1_vector)

    # Update manipulators position
    distance_input.setManipulator(origin_point, direction_vector)
    angle_input.setManipulator(origin_point, perp1_vector, perp2_vector)

    if (
        occs_input.selectionCount > 0
        and direction_input.selectionCount > 0
        and origin_input.selectionCount > 0
    ):
        distribution_input.isVisible = True
        distribution_input.isEnabled = True
        quantity_input.isVisible = True
        quantity_input.isEnabled = True
        distance_input.isVisible = True
        distance_input.isEnabled = True
        angle_input.isVisible = True
        angle_input.isEnabled = True
    else:
        distribution_input.isEnabled = False
        quantity_input.isEnabled = False
        distance_input.isEnabled = False
        angle_input.isEnabled = False


# This event handler is called when the user interacts with any of the inputs in the dialog
# which allows you to verify that all of the inputs are valid and enables the OK button.
def command_validate_input(args: adsk.core.ValidateInputsEventArgs):
    # General logging for debug.
    futil.log(f"{CMD_NAME} Validate Input Event")

    inputs = args.inputs

    # Verify the validity of the inputs. This controls if the OK button is enabled or not.
    occs_input = inputs.itemById("occs")
    direction_input = inputs.itemById("direction")
    origin_input = inputs.itemById("origin")

    if (
        occs_input
        and occs_input.selectionCount > 0
        and direction_input
        and direction_input.selectionCount > 0
        and origin_input
        and origin_input.selectionCount > 0
    ):
        args.areInputsValid = True
    else:
        args.areInputsValid = False


# This event handler is called when the command terminates.
def command_destroy(args: adsk.core.CommandEventArgs):
    # General logging for debug.
    futil.log(f"{CMD_NAME} Command Destroy Event")

    global local_handlers
    local_handlers = []


def calculate_pattern(inputs: adsk.core.CommandInputs):
    product = app.activeProduct

    if not isinstance(product, adsk.fusion.Design):
        raise ValueError("This command is only available within a Fusion design.")

    design = adsk.fusion.Design.cast(product)
    parent_component = design.activeComponent

    occs_input = adsk.core.SelectionCommandInput.cast(inputs.itemById("occs"))

    direction_input = adsk.core.SelectionCommandInput.cast(inputs.itemById("direction"))
    direction_vector = adsk.fusion.ConstructionAxis.cast(
        direction_input.selection(0).entity
    ).geometry.direction

    origin_input = adsk.core.SelectionCommandInput.cast(inputs.itemById("origin"))
    origin_point = adsk.fusion.ConstructionPoint.cast(
        origin_input.selection(0).entity
    ).geometry

    distribution_input = adsk.core.DropDownCommandInput.cast(
        inputs.itemById("distribution")
    )
    distribution_type = distribution_input.selectedItem.name

    quantity_input = adsk.core.IntegerSpinnerCommandInput.cast(
        inputs.itemById("quantity")
    )
    quantity = quantity_input.value

    distance_input = adsk.core.DistanceValueCommandInput.cast(
        inputs.itemById("distance")
    )
    distance = distance_input.value
    distanceIn_between = distance
    if distribution_type == "Extent":
        distanceIn_between = distance / quantity

    angle_input = adsk.core.AngleValueCommandInput.cast(inputs.itemById("angle"))
    angle = angle_input.value

    is_new_copy_input = adsk.core.BoolValueCommandInput.cast(
        inputs.itemById("isNewCopy")
    )
    is_new_copy = is_new_copy_input.value

    for n in range(quantity - 1):
        for i in range(occs_input.selectionCount):
            occurrence = adsk.fusion.Occurrence.cast(occs_input.selection(i).entity)
            futil.log(f"Selected occurrence: {occurrence.name}")

            transform = adsk.core.Matrix3D.create()
            translation_vector = direction_vector.copy()
            translation_vector.normalize()
            translation_vector.scaleBy(distanceIn_between * (n + 1))
            transform.translation = translation_vector

            rotation = adsk.core.Matrix3D.create()
            rotation.setToRotation(angle * (n + 1), direction_vector, origin_point)
            transform.transformBy(rotation)

            # Copy the occurrence and transform it
            if is_new_copy:
                parent_component.occurrences.addNewComponentCopy(
                    occurrence.component, transform
                )
            else:
                parent_component.occurrences.addExistingComponent(
                    occurrence.component, transform
                )
