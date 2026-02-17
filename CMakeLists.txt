# cmake_minimum_required(VERSION 3.13.4)

# project(LungSegmentation)

# find_package(Slicer REQUIRED)
# include(${Slicer_USE_FILE})

# add_subdirectory(LungSegmentation)

#--------------------------------------------------------------
set(MODULE_NAME "LungSegmentation")

#-------------------------------------------------------------
set(MODULE_PYTHON_SCRIPTS
  ${MODULE_NAME}.py
  )

set(MODULE_RESOURCES 
  Resources/Icons/${MODULE_NAME}.png
  Resources/scripts/nnunet_runner.py 
  Resources/UI/${MODULE_NAME}.ui
)

slicerMacroBuildScriptedModule(
  NAME ${MODULE_NAME}
  SCRIPTS ${MODULE_PYTHON_SCRIPTS}
  RESOURCES ${MODULE_RESOURCES} 
  )