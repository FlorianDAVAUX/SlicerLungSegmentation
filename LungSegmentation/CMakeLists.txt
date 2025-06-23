####################################################
set(MODULE_NAME "LungSegmentation")

####################################################
set(MODULE_UI_FILES
  Resources/UI/LungSegmentation.ui
)

####################################################
set(MODULE_PYTHON_SCRIPTS
  ${MODULE_NAME}.py
)

####################################################
set(MODULE_RESOURCES
  Resources/Icons/LungSegmentation.png
  Resources/models.json
)

####################################################
slicer_add_qt_scripted_module(
  NAME ${MODULE_NAME}
  SCRIPTS ${MODULE_PYTHON_SCRIPTS}
  UI_FILES ${MODULE_UI_FILES}
  RESOURCES ${MODULE_RESOURCES}
  RESOURCE_PREFIX ${MODULE_NAME}
)
