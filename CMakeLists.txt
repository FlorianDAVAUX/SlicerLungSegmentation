cmake_minimum_required(VERSION 3.13.4)

project(LungSegmentation)

# Recherche Slicer
find_package(Slicer REQUIRED)
include(${Slicer_USE_FILE})

# Ajoute le module LungSegmentation
add_subdirectory(LungSegmentation)
