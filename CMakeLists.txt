cmake_minimum_required(VERSION 3.13.4)

project(LungSegmentation)

find_package(Slicer REQUIRED)
include(${Slicer_USE_FILE})

add_subdirectory(LungSegmentation)
