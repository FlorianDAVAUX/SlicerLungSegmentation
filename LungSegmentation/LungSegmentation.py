import os
import re
import site
import textwrap
import qt
import sys
import vtk
import slicer
import platform
import subprocess
import shutil
import zipfile
import json
import tarfile
import logging
import urllib
import slicer
import tempfile
import threading
import importlib.util
from slicer.ScriptedLoadableModule import *
import importlib.resources as resources
from importlib.metadata import version, PackageNotFoundError
from qt import QTimer, QTreeView, QFileSystemModel, QPushButton, QFileDialog, QMessageBox, Signal, QObject


###################################################### Object for signals to know if the segmentation is finished or if there is an error ######################################################

class SegmentationSignals(QObject):
    """
    Signals for segmentation

    Args:
        None
    Returns:
        None
    """
    finished = Signal(bool)
    error = Signal(str)
    progress = Signal(int)

###################################################### Main class of the module ######################################################

class LungSegmentation(ScriptedLoadableModule):
    """
    Lung segmentation module
    """
    def __init__(self, parent):
        """
        Constructor module

        Args:
            parent (QWidget): Parent widget, default is None.
        Returns:
            None
        """
        parent.title = "LungSegmentation"
        parent.categories = [""]
        parent.contributors = ["Florian Davaux (CREATIS)"]
        parent.helpText = "Automatic segmentation of pulmonary structures"
        parent.acknowledgementText = "KOLOR SPCCT project"
        self.parent = parent
        self.imagesTs_path = None
        self.parent.icon = qt.QIcon(os.path.join(os.path.dirname(__file__), 'Resources', 'Icons', 'LungSegmentation.png'))
        

####################################################### Class for the module's graphical interface ######################################################

class LungSegmentationWidget(ScriptedLoadableModuleWidget):
    """
    Widget for the graphical interface of the lung segmentation module
    """
    def __init__(self, parent=None):
        """
        Widget constructor

        Args:
            parent (QWidget): Parent widget, default is None.
        Returns:
            None
        """
        ScriptedLoadableModuleWidget.__init__(self, parent)

        self.timer = qt.QTimer()
        self.timer.setInterval(500)
        self.timer.timeout.connect(self.updateProgressBar)

        self.progressValue = 0
        self.progressDuration = 6 * 60  
        self.elapsedSeconds = 0

        self.signals = SegmentationSignals()
        self.signals.finished.connect(self.on_segmentation_finished)
        self.signals.error.connect(self.on_segmentation_error)

        self.input_path = None              # Path to the input file
        self.input_node = None              # Input volume node
        self.models_dir = None              # Folder containing the downloaded models
        self.structure_to_segment = None    # Structure to segment
        self.tmp_file = None                # Temporary file to store the path of the dataset json 
        self.name = None                    # Name of the future prediction

        self.convertedInputToDelete = None  # For future deletion

    def setup(self):
        """
        Called when the application opens the module the first time and the widget is initialized.

        Args:
            None
        Returns:
            None
        """
        self.install_dependencies_if_needed()
        ScriptedLoadableModuleWidget.setup(self)

        # Load the UI
        self.extensionPath = os.path.dirname(__file__)
        uiFilePath = os.path.join(self.extensionPath, 'Resources', 'UI', 'LungSegmentation.ui')
        uiWidget = slicer.util.loadUI(uiFilePath)
        self.layout.addWidget(uiWidget)
        
        # Map UI elements to self.ui
        self.ui = slicer.util.childWidgetVariables(uiWidget)
        self.layout.setContentsMargins(0, 0, 0, 0)

        # UI Initialization
        self.ui.progressBar.setVisible(False)
        self.ui.progressBar.setValue(0)

        # Connections
        self.ui.browseInputButton.clicked.connect(lambda: self.openDialog("input"))
        self.ui.browseOutputButton.clicked.connect(lambda: self.openDialog("output"))
        self.ui.pushButtonSegmentation.clicked.connect(self.onSegmentationButtonClicked)

        # Helper Collections
        self.allCheckBoxes = uiWidget.findChildren(qt.QCheckBox)

        # The only package that requires a strict version check
        strict_requirements = {
            "nnUNet_package": "0.3.4"
        }

    def install_dependencies_if_needed(self):
        """
        Checks if required packages are installed.
        Relies on pip's native dependency resolution to avoid hardcoding sub-packages.
        """

        # ONLY list your direct, top-level requirements here.
        # You can pin specific versions directly in the string.
        requirements = [
            "nnUNet_package": "0.3.4",
            "nnunetv2",
            "dicom2nifti"
        ]

        def has_nvidia_gpu():
            """Efficiently checks for an NVIDIA GPU driver without requiring admin rights."""
            current_os = platform.system()
            if current_os == "Windows":
                import ctypes
                try:
                    ctypes.windll.LoadLibrary("nvcuda.dll")flo_desktop
                    return True
                except OSError:
                    return False
            elif current_os == "Linux":
                return os.path.exists("/proc/driver/nvidia") or os.path.exists("/dev/nvidiactl")
            return False

        # --- OS AND HARDWARE ROUTING ---
        current_system = platform.system()

        # 1. Handle Triton (Linux only)
        if current_system == "Linux":
            requirements.append("triton")
            print("Linux OS detected. Appending Triton.")

        # 2. Handle CUDA (Append the top-level CUDA runtime, pip handles the rest)
        if has_nvidia_gpu():
            # You only need the primary CUDA package; it will pull in cupti, cublas, etc.
            requirements.append("nvidia-cuda-runtime-cu12")
            print("NVIDIA CUDA driver detected. Appending CUDA dependencies.")

        # --- INSTALLATION LOGIC ---
        packages_to_install = []

        for req in requirements:
            # Extract the package name without the version pin (e.g., 'nnunetv2' from 'nnunetv2==0.3.4')
            pkg_name = req.split("==")[0].split(">=")[0]
            
            try:
                installed_version = version(pkg_name)
                # If you have a strict pin (==), check if it matches
                if "==" in req:
                    required_ver = req.split("==")[1]
                    if installed_version != required_ver:
                        packages_to_install.append(req)
            except PackageNotFoundError:
                packages_to_install.append(req)

        # Install missing packages
        if packages_to_install:
            print(f"\nInstalling packages (dependencies will be resolved automatically): {packages_to_install}")
            
            # NOTICE: "--no-deps" has been removed so pip resolves dependencies automatically
            cmd = [sys.executable, "-m", "pip", "install"] + packages_to_install
            
            try:
                subprocess.check_call(cmd)
                
                # Restart notification
                msg = "Dependencies have been installed.\nSlicer will close automatically. Please relaunch it."
                print(msg)
                slicer.util.messageBox(msg)
                slicer.util.mainWindow().close()
                sys.exit(0)
                
            except subprocess.CalledProcessError as e:
                error_msg = f"Failed to install dependencies.\nCommand: {' '.join(cmd)}"
                print(f"  [ERROR] {error_msg}")
                slicer.util.errorDisplay("An error occurred while installing packages. Check the Python console.")
        else:
            print("\nAll top-level dependencies are correctly installed.")
    
    def openDialog(self, which):
        """
        Opens a dialog box to select a file or folder.

        Args:
            which (str): "input" to select an input file, "output" to select an output folder.
        
        Returns:
            None
        """
        if which == "input":
            selectedPath = self.selectInputFile()
            if selectedPath:
                self.ui.inputLineEdit.setText(selectedPath)

        elif which == "output":
            selectedDir = qt.QFileDialog.getExistingDirectory(
                slicer.util.mainWindow(),
                "Select an output folder",
                ""
            )
            if selectedDir:
                self.ui.outputLineEdit.setText(selectedDir)

    def selectInputFile(self):
        """
        Displays a dialog box to select an image file or a DICOM folder.
        Does not perform conversion here, just stores the original path.

        Args:
            None
        Returns:
            str: Path to the selected file or folder.
        """
        optionsBox = qt.QMessageBox(slicer.util.mainWindow())
        optionsBox.setWindowTitle("Choose image source")
        optionsBox.setText("Select the input type:")
        imageButton = optionsBox.addButton("Image file (.nrrd, .nii, .mha...)", qt.QMessageBox.ActionRole)
        dicomButton = optionsBox.addButton("DICOM folder", qt.QMessageBox.ActionRole)
        optionsBox.addButton("Cancel", qt.QMessageBox.RejectRole)
        optionsBox.exec_()

        clicked = optionsBox.clickedButton()
        if clicked == imageButton:
            path = self.handleImageSelection()
        elif clicked == dicomButton:
            path = self.handleDICOMSelection()
        else:
            return
        
        self.ui.inputLineEdit.setText(path)


    def safeLoadVolume(self, path):
        """
        Loads a volume in a way compatible with recent and older versions of Slicer.
        Returns the loaded node or None on failure.

        Args:
            path (str): Path to the image file.
        Returns:
            vtkMRMLScalarVolumeNode: Loaded volume node.
        """
        self.input_node = slicer.util.loadVolume(path)
        return self.input_node


    def handleImageSelection(self):
        """
        Selects an image file, loads it into the viewer, without immediate conversion.

        Args:
            None
        Returns:
            str: Path to the selected image file.
        """
        selected = qt.QFileDialog.getOpenFileName(
            slicer.util.mainWindow(),
            "Select an image",
            "",
            "Images (*.nrrd *.nii *.nii.gz *.mha)"
        )
        if not selected:
            return None

        node = self.safeLoadVolume(selected)
        if not node:
            qt.QMessageBox.critical(slicer.util.mainWindow(), "Error", "Could not load the selected file.")
            return None

        return selected


    def handleDICOMSelection(self):
        """
        Selects a DICOM folder, loads the first file into the viewer, without immediate conversion.

        Args:
            None
        Returns:
            str: Path to the selected DICOM folder.
        """
        dicomDir = qt.QFileDialog.getExistingDirectory(
            slicer.util.mainWindow(),
            "Select a DICOM folder",
            ""
        )   
        if not dicomDir:
            return None

        dcmFiles = [os.path.join(dicomDir, f) for f in os.listdir(dicomDir) if f.lower().endswith(".dcm")]
        if not dcmFiles:
            qt.QMessageBox.critical(slicer.util.mainWindow(), "Error", "No DICOM file found.")
            return None

        node = self.safeLoadVolume(dcmFiles[0])
        if not node:
            qt.QMessageBox.critical(slicer.util.mainWindow(), "Error", "Failed to load DICOM file.")
            return None

        return dicomDir

    
    def prepareInputForSegmentation(self, inputPath):
        """
        Checks and prepares the input path for segmentation.
        If necessary, converts to .nrrd and returns the converted path.

        Args:
            inputPath (str): Path to the input file or folder.
        
        Returns:
            str: Path to the .nrrd file ready for segmentation.
        """
        inputPath = inputPath.strip()
        if not inputPath or not os.path.exists(inputPath):
            raise RuntimeError("Invalid input path.")

        ext = os.path.splitext(inputPath)[1].lower()
        is_dir = os.path.isdir(inputPath)

        if is_dir:
            # DICOM folder
            dcmFiles = [os.path.join(inputPath, f) for f in os.listdir(inputPath) if f.lower().endswith(".dcm")]
            if not dcmFiles:
                raise RuntimeError("No DICOM file found in the folder.")
            success, volumeNode = slicer.util.loadVolume(dcmFiles[0], returnNode=True)
            if not success:
                raise RuntimeError("Error loading DICOM volume.")
            convertedPath = os.path.join(slicer.app.temporaryPath, "converted_from_dicom.nrrd")
            slicer.util.saveNode(volumeNode, convertedPath)
            self.convertedInputToDelete = convertedPath
            return convertedPath

        elif ext in [".mha", ".nii", ".nii.gz"]:
            # Image file to convert
            success, volumeNode = slicer.util.loadVolume(inputPath, returnNode=True)
            if not success:
                raise RuntimeError("Error loading image.")
            convertedPath = os.path.join(slicer.app.temporaryPath, "converted_from_image.nrrd")
            slicer.util.saveNode(volumeNode, convertedPath)
            self.convertedInputToDelete = convertedPath
            return convertedPath

        elif ext == ".nrrd":
            return inputPath

        else:
            raise RuntimeError("Unsupported format. Please select a .nrrd, .mha, .nii file, or a DICOM folder.")

    def _get_active_checkbox_name(self):
        """
        Helper: Returns the lowercased objectName of the currently checked box.
        Returns None if no box is checked.

        Args:
            None
        Returns:
            str: The name of the active checkbox, lowercased.
        """
        for cb in self.allCheckBoxes:
            if cb.isChecked():
                return str(cb.objectName).lower()
        return ""

    def check_mode(self):
        """
        Checks the segmentation mode (in vivo, ex vivo or axial).

        Args:
            None
        Returns:
            str: "invivo", "exvivo" or "axial"
        """
        name = self._get_active_checkbox_name()

        if "invivo" in name:
            return "invivo"
        elif "exvivo" in name:
            return "exvivo"
        elif "axial" in name:
            return "axial"

        return None

    def check_animal(self):
        """
        Checks the animal to segment.

        Args:
            None
        Returns:
            str: "pig", "rat" or "rabbit"
        """
        name = self._get_active_checkbox_name()
        
        if "rabbit" in name:
            return "rabbit"
        elif "pig" in name:
            return "pig"
        elif "rat" in name:
            return "rat"
        
        return None
                        

    def check_structure(self):
        """
        Checks the pulmonary structure to segment.

        Args:
            None 
        Returns:
            str: "parenchyma", "airways", "vascular", "lobes", "parenchymaairways", "all"
        """
        name = self._get_active_checkbox_name()
        if not name:
            return None
        
        # We need to set double keys name -> result because some checkboxes have names that are substrings of others (e.g. "parenchyma" and "parenchymaairways")
        checks = [
            ("parenchymaairwayskidneysheart", "parenchymaairwayskidneysheart"),
            ("parenchymaairwaysvascular", "all"),
            ("all", "all"), 
            ("parenchymaairways", "parenchymaairways"),
            ("parenchyma", "parenchyma"),
            ("emptylobes", "emptylobes"),
            ("airways", "airways"),
            ("vascular", "vascular"),
            ("lobes", "lobes")
        ]

        for substring, result in checks:
            if substring in name:
                return result
        
        return None

        
    def onSegmentationButtonClicked(self):
        """
        Function called when the segmentation button is clicked.
        It prepares the parameters and starts the segmentation in the background.

        Args:
            None
        Returns:
            None
        """
        
        # Check if it is Invivo, Exvivo or Axial
        mode = self.check_mode()

        # Check if it is Pig or Rabbit
        animal = self.check_animal()

        # Check the structure to segment
        self.structure_to_segment = self.check_structure()
        
        print("\nStarting segmentation...")

        try:
            self.input_path = self.prepareInputForSegmentation(self.ui.inputLineEdit.text)
        except Exception as e:
            qt.QMessageBox.critical(slicer.util.mainWindow(), "Input Error", str(e))
            return

        output_path = self.ui.outputLineEdit.text

        if not os.path.isfile(self.input_path) or not self.input_path.endswith('.nrrd'):
            qt.QMessageBox.critical(slicer.util.mainWindow(), "File Error", "Please select a valid NRRD input file.")
            return

        extension_dir = os.path.dirname(__file__)
        self.models_dir = os.path.join(extension_dir, "models")

        self.ui.progressBar.setVisible(True)
        self.ui.progressBar.setValue(0)
        self.progressValue = 0
        self.elapsedSeconds = 0

        qt.QTimer.singleShot(0, self.timer.start)

        self.start_segmentation(mode, output_path, animal)
    

    def start_segmentation(self, mode, output_path, animal):
        """
        Function that starts the segmentation process in the background.
        
        It calls the nnunet_runner.py script with the segmentation parameters.
        It waits for the process to finish, then emits the finished signal if everything goes well,
        or the error signal if a problem occurs.
        
        Args:
            mode (str): Segmentation mode (In vivo, Ex vivo)
            input_path (str): Path to the input file
            output_path (str): Path to the output folder
            animal (str): Name of the animal
        Returns:
            None
        """
        def worker():
            """
            Worker function that starts the segmentation process in the background.
            
            It calls the nnunet_runner.py script with the segmentation parameters.
            It waits for the process to finish, then emits the finished signal if everything goes well,
            or the error signal if a problem occurs.

            Args:
                None
            Returns:
                None
            """
            try:
                from pathlib import Path
                module_dir = os.path.dirname(__file__)
                runner_path = os.path.join(module_dir, "Resources", "scripts", "nnunet_runner.py")

                # Temporary file to store the path of the dataset json
                self.tmp_file = os.path.join(tempfile.gettempdir(), "nnunet_context.json")
                if os.path.exists(self.tmp_file):
                    os.remove(self.tmp_file)
                
                cmd = [
                    sys.executable, str(runner_path),
                    "--mode", mode,
                    "--structure", self.structure_to_segment,
                    "--input", self.input_path,
                    "--output", output_path,
                    "--models_dir", self.models_dir,
                    "--animal", animal,
                    "--tmp_file", self.tmp_file
                ]
                subprocess.run(cmd, text=True)
                self.signals.finished.emit(True)
            except subprocess.CalledProcessError as e:
                self.signals.error.emit(str(e))

        threading.Thread(target=worker, daemon=True).start()


    def on_segmentation_error(self, error_message):
        """
        Function called in case of an error during segmentation.
        It stops the timer, updates the progress bar and displays an error message.
        
        Args:
            error_message (str): Error message to display.
        Returns:
            None
        """
        self.timer.stop()
        self.ui.progressBar.setVisible(False)
        slicer.util.errorDisplay(f"Error during segmentation :\n{error_message}")


    def on_segmentation_finished(self, success):
        """
        Function called when segmentation is finished.
        It stops the timer, updates the progress bar and displays a success message.
        
        Args:
            success (bool): Indicates whether the segmentation was successful or not.
        Returns:
            None
        """
        self.timer.stop()
        self.ui.progressBar.setValue(100)
        self.ui.progressBar.setVisible(False)

        if success:
            self.load_prediction(self.ui.outputLineEdit.text)
            slicer.util.infoDisplay("Segmentation finished successfully.")
        
    def updateProgressBar(self):
        """
        Updates the progress bar every second.
        If the progress duration is exceeded, the bar is blocked at 99% until segmentation is finished.

        Args:
            None
        Returns:
            None
        """
        if self.elapsedSeconds >= self.progressDuration:
            self.ui.progressBar.setValue(99)
            return
        
        self.elapsedSeconds += 1
        progress = int((self.elapsedSeconds / self.progressDuration) * 99)
        self.ui.progressBar.setValue(progress)


    def load_prediction(self, output_path):
        """
        Loads the prediction generated by nnUNet into Slicer.

        Args:
            output_path (str): Path to the output folder where the prediction is saved.
        Returns:
            None
        """
        prediction_path = os.path.join(output_path, "001.nrrd")
        if not os.path.exists(prediction_path):
            qt.QMessageBox.warning(slicer.util.mainWindow(), "Error", "No prediction found to load.")
            return
        else:
            seg_name = self.structure_to_segment
            self.convert_prediction_to_segmentation(prediction_path, output_path, seg_name)
                
    def convert_prediction_to_segmentation(self, prediction_path, output_path, segmentation_name):
        """
        Converts an nnUNet prediction (.nrrd) to Slicer segmentation
        while strictly maintaining the same geometry.

        Args:
            prediction_path (str): Path to the prediction file (.nrrd).
            output_path (str): Output folder to save the segmentation.
            segmentation_name (str): Name to give to the segmentation. 
        Returns:
            str: Path to the saved segmentation file.
        """

        # Load the prediction as a labelmap
        labelmapNode = slicer.util.loadLabelVolume(prediction_path)
        labelmapNode.SetName(segmentation_name + "_labelmap")

        # Create a segmentation node
        segmentationNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode", segmentation_name)
        segmentationNode.CreateDefaultDisplayNodes()
        
        # Force the same geometry
        segmentationNode.SetReferenceImageGeometryParameterFromVolumeNode(labelmapNode)

        # Import the labelmap without modifying size
        slicer.modules.segmentations.logic().ImportLabelmapToSegmentationNode(labelmapNode, segmentationNode)

        # Check and rename segments according to the label_map
        segment_ids = vtk.vtkStringArray()
        segmentationNode.GetSegmentation().GetSegmentIDs(segment_ids)

        slicer.mrmlScene.RemoveNode(labelmapNode)

        with open(self.tmp_file, 'r') as f:
            data = json.load(f)
        dataset_json_path = data["dataset_json_path"]

        # Load the model's dataset.json
        with open(dataset_json_path, "r") as f:
            dataset = json.load(f)

        raw_label_map = dataset.get("labels", {})
        label_map = {int(v): k for k, v in raw_label_map.items() if int(v) > 0}

        for i in range(segment_ids.GetNumberOfValues()):
            segment_id = segment_ids.GetValue(i)
            segment = segmentationNode.GetSegmentation().GetSegment(segment_id)
            label_index = i + 1
            name = label_map.get(label_index, f"Class_{label_index}")
            segment.SetName(name)

        displayNode = segmentationNode.GetDisplayNode()
        if displayNode:
            displayNode.SetVisibility(False)

        segmentation_path = os.path.join(output_path, segmentation_name + ".nrrd")
        slicer.util.saveNode(segmentationNode, segmentation_path)
        os.remove(prediction_path)

        # Clean up temporary converted input if any
        if self.convertedInputToDelete and os.path.exists(self.convertedInputToDelete):
            try:
                os.remove(self.convertedInputToDelete)
            except Exception as e:
                print(f"Error deleting converted input: {e}")
            finally:
                self.convertedInputToDelete = None

    def run_automated_task(self, volumeNode, animal, mode="invivo", structure="all"):
        """
        Main function to run the automated segmentation task with given parameters.
        It prepares the input, configures paths, and starts the segmentation process.

        Args:
            volumeNode (vtkMRMLScalarVolumeNode): The input volume node to segment.
            animal (str): The animal type ("pig", "rat", "rabbit").
            mode (str): The segmentation mode ("invivo", "exvivo", "axial").
            structure (str): The structure to segment ("parenchyma", "airways", "vascular", "lobes", "parenchymaairways", "all").
        Returns:
            None
        """
        print(f"Animal : {animal} | Mode : {mode} | Structure : {structure}")
        
        self.structure_to_segment = structure
        self.input_node = volumeNode
        
        # Create a temporary directory to store the converted input and output results
        temp_dir = tempfile.mkdtemp(prefix=f"AutoSeg_{animal}_")
        self.input_path = os.path.join(temp_dir, "input_volume.nrrd")
        slicer.util.saveNode(volumeNode, self.input_path)
        self.convertedInputToDelete = self.input_path

        # Directory to store results
        output_path = os.path.join(temp_dir, "output")
        os.makedirs(output_path, exist_ok=True)
        
        # UI updates
        self.ui.outputLineEdit.setText(output_path)

        # Finding the models directory
        extension_dir = os.path.dirname(__file__)
        self.models_dir = os.path.join(extension_dir, "models")

        # Progress bar initialization
        self.ui.progressBar.setVisible(True)
        self.ui.progressBar.setValue(0)
        self.progressValue = 0
        self.elapsedSeconds = 0
        qt.QTimer.singleShot(0, self.timer.start)

        # Start the segmentation
        self.start_segmentation(mode, output_path, animal)