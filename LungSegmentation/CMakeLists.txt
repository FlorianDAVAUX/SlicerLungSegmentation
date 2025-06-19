cmake_minimum_required(VERSION 3.13.4)

project(LungSegmentation)

# -----------------------------------------------------------------------------
# Extension meta-information
# -----------------------------------------------------------------------------

set(EXTENSION_HOMEPAGE "https://github.com/FlorianDAVAUX/SlicerLungSegmentation")
set(EXTENSION_CATEGORY "Segmentation")
set(EXTENSION_CONTRIBUTORS "Florian Davaux (CPE Lyon, CREATIS)")
set(EXTENSION_DESCRIPTION "Segmentation des structures pulmonaires avec nnU-Netv2.")
set(EXTENSION_ICONURL "https://github.com/FlorianDAVAUX/SlicerLungSegmentation/blob/main/LungSegmentation/Resources/Icons/LungSegmentation.png")
set(EXTENSION_SCREENSHOTURLS "")
set(EXTENSION_DEPENDS "")  # Liste de dépendances Slicer (autres extensions), si nécessaire
set(EXTENSION_BUILD_SUBDIRECTORY .)

# -----------------------------------------------------------------------------
# Extension setup
# -----------------------------------------------------------------------------

find_package(Slicer REQUIRED)
include(${Slicer_USE_FILE})

slicer_add_python_module(
  SCRIPT_DIR LungSegmentation
  SCRIPTS ${LungSegmentation_SRCS}
)

slicer_add_qt_scripted_module(
  NAME LungSegmentation
  SCRIPTS ${LungSegmentation_SRCS}
  RESOURCES ${LungSegmentation_RESOURCES}
  UI_RESOURCES ${LungSegmentation_UI_RESOURCES}
)

# -----------------------------------------------------------------------------
# Additional build settings
# -----------------------------------------------------------------------------

slicer_extension_add(LungSegmentation)
