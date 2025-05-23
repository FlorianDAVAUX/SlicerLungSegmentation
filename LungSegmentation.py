import os
import qt
import slicer
import subprocess
import shutil
import zipfile
import json
import logging
import urllib
import sys
import slicer
import tempfile
from slicer.ScriptedLoadableModule import *
from qt import QTreeView, QFileSystemModel, QPushButton, QFileDialog

class LungSegmentation(ScriptedLoadableModule):
    def __init__(self, parent):
        parent.title = "LungSegmentation"
        parent.categories = ["Segmentation"]
        parent.contributors = ["Florian Davaux (CREATIS)"]
        parent.helpText = "Segmentation automatique des structures pulmonaires"
        parent.acknowledgementText = "Projet KOLOR SPCCT"
        self.parent = parent
        self.imagesTs_path = None
        self.parent.icon = qt.QIcon(os.path.join(os.path.dirname(__file__), 'Resources', 'Icons', 'LungSegmentation.png'))


class LungSegmentationWidget(ScriptedLoadableModuleWidget):
    def setup(self):
        self.install_dependencies_if_needed()
        ScriptedLoadableModuleWidget.setup(self)

        self.extensionPath = os.path.dirname(__file__)
        uiFilePath = os.path.join(self.extensionPath, 'Resources', 'UI', 'LungSegmentation.ui')
        
        # Chargement correct de l'UI
        uiWidget = slicer.util.loadUI(uiFilePath)
        self.layout.addWidget(uiWidget)
        self.layout.setContentsMargins(0, 0, 0, 0)


        # Récupération des widgets
        self.checkBoxInvivoParenchyma = uiWidget.findChild(qt.QCheckBox, "checkBoxInvivoParenchyma")
        self.checkBoxInvivoAirways = uiWidget.findChild(qt.QCheckBox, "checkBoxInvivoAirways")
        self.checkBoxInvivoVascularTree = uiWidget.findChild(qt.QCheckBox, "checkBoxInvivoVascularTree")

        self.checkBoxExvivoParenchyma = uiWidget.findChild(qt.QCheckBox, "checkBoxExvivoParenchyma")
        self.checkBoxExvivoAirways = uiWidget.findChild(qt.QCheckBox, "checkBoxExvivoAirways")


        self.browseInputButton = uiWidget.findChild(qt.QPushButton, "browseInputButton")
        self.lineEditInputPath = uiWidget.findChild(qt.QLineEdit, "inputLineEdit")

        self.browseOutputButton = uiWidget.findChild(qt.QPushButton, "browseOutputButton")
        self.lineEditOutputPath = uiWidget.findChild(qt.QLineEdit, "outputLineEdit")

        self.segmentationButton = uiWidget.findChild(qt.QPushButton, "pushButtonSegmentation")

        # Connexions
        for checkbox in [self.checkBoxInvivoParenchyma, self.checkBoxInvivoAirways, self.checkBoxInvivoVascularTree,
                 self.checkBoxExvivoParenchyma, self.checkBoxExvivoAirways]:
            checkbox.toggled.connect(lambda state, cb=checkbox: self.validateCheckboxes(cb))

        self.browseInputButton.clicked.connect(lambda: self.openDialog("input"))
        self.browseOutputButton.clicked.connect(lambda: self.openDialog("output"))
        self.segmentationButton.clicked.connect(self.onSegmentationButtonClicked)
    
    def install_dependencies_if_needed(self):
        required_packages = {
            "torch": "torch",
            "numpy": "numpy",
            "scikit-learn": "sklearn",
            "SimpleITK": "SimpleITK",
            "nibabel": "nibabel",
            "tqdm": "tqdm",
            "blosc2": "blosc2",
            "acvl-utils": "acvl_utils",
            "nnunetv2": "nnunetv2"
        }

        missing_packages = []

        # Vérification de l'importabilité des modules
        for pip_name, import_name in required_packages.items():
            try:
                __import__(import_name)
            except ImportError:
                missing_packages.append(pip_name)

        if not missing_packages:
            print("✅ Tous les paquets requis sont installés.")
            return

        # Afficher la boîte de dialogue pour installation
        install = qt.QMessageBox.question(
            slicer.util.mainWindow(),
            "Modules manquants",
            f"Les modules suivants sont manquants :\n{', '.join(missing_packages)}\nVoulez-vous les installer maintenant ?",
            qt.QMessageBox.Yes | qt.QMessageBox.No
        )
        if install == qt.QMessageBox.Yes:
            try:
                python_exec = sys.executable
                for pkg in missing_packages:
                    subprocess.check_call([python_exec, "-m", "pip", "install", pkg])
                qt.QMessageBox.information(
                    slicer.util.mainWindow(), "Installation réussie",
                    "Les dépendances manquantes ont été installées avec succès."
                )
            except subprocess.CalledProcessError as e:
                qt.QMessageBox.critical(
                    slicer.util.mainWindow(), "Échec de l'installation",
                    f"Erreur pendant l'installation :\n{str(e)}"
                )
        else:
            qt.QMessageBox.warning(
                slicer.util.mainWindow(), "Modules manquants",
                "Vous devez installer les dépendances pour utiliser cette extension."
            )

    def openDialog(self, which):
        """
        Ouvre une boîte de dialogue pour choisir un dossier.
        :param which: "input" pour le dossier d'entrée, "output" pour le dossier de sortie.
        """
        directory = qt.QFileDialog.getExistingDirectory(None, "Choisir un dossier", "")
        if directory:
            if which == "input":
                self.lineEditInputPath.setText(directory)
            elif which == "output":
                self.lineEditOutputPath.setText(directory)

    def validateCheckboxes(self, sender):
        invivoChecked = (
            self.checkBoxInvivoParenchyma.checked or
            self.checkBoxInvivoAirways.checked or
            self.checkBoxInvivoVascularTree.checked
        )
        exvivoChecked = (
            self.checkBoxExvivoParenchyma.checked or
            self.checkBoxExvivoAirways.checked
        )

        # Si les deux groupes sont sélectionnés, avertir
        if invivoChecked and exvivoChecked:
            qt.QMessageBox.warning(slicer.util.mainWindow(), "Conflit de sélection",
                                "Veuillez sélectionner uniquement Invivo ou Exvivo, pas les deux.")
            # Décocher tout sauf le dernier cliqué
            for checkbox in [
                self.checkBoxInvivoParenchyma, self.checkBoxInvivoAirways, self.checkBoxInvivoVascularTree,
                self.checkBoxExvivoParenchyma, self.checkBoxExvivoAirways
            ]:
                if checkbox != sender:
                    checkbox.setChecked(False)
    
    def loadConfig(self):
        config_path = os.path.join(os.path.dirname(__file__), 'Resources', 'models.json')
        with open(config_path, 'r') as f:
            return json.load(f)
    
    def onSegmentationButtonClicked(self):
        print("\n Lancement de la segmentation")
        
        config = self.loadConfig()
        model_url = config["model_url"]
        model_id = config["model_id"]
        configuration = config["configuration"]
        fold = str(config["fold"])
        model_name = config["model_name"]

        input_path = self.lineEditInputPath.text
        output_path = self.lineEditOutputPath.text
        
        # On récupère le chemin temporaire de Slicer, si disponible sinon on utilise le tempdir
        temp_path = slicer.app.temporaryPath if slicer.app.temporaryPath else tempfile.gettempdir()

        model_zip_path = os.path.join(temp_path, model_name + ".zip")
        extracted_model_path = os.path.join(temp_path, model_name)

        # Télécharger le modèle si nécessaire
        if not os.path.exists(model_zip_path):
            print("\n 🔽 Téléchargement du modèle depuis GitHub...")
            urllib.request.urlretrieve(model_url, model_zip_path)
            print("\n ✅ Modèle téléchargé")

        # Extraire le modèle
        if not os.path.exists(extracted_model_path):
            with zipfile.ZipFile(model_zip_path, 'r') as zip_ref:
                zip_ref.extractall(extracted_model_path)
        

        self.edit_json_for_prediction(extracted_model_path, input_path)

        this_file_path = os.path.abspath(__file__)
        resources_dir = os.path.join(os.path.dirname(this_file_path), "Resources", "nnUNet")

        os.environ["nnUNet_results"] = os.path.abspath(extracted_model_path)

        # Lancer la prédiction
        subprocess.run([
            "nnUNetv2_predict",
            "-i", self.imagesTs_path,
            "-o", output_path,
            "-d", model_id,
            "-c", configuration,
            "-f", fold
        ], check=True)

        qt.QMessageBox.information(slicer.util.mainWindow(), "Terminé", "Segmentation terminée avec succès.")


    def edit_json_for_prediction(self, extracted_model_path, input_path):

        # Trouver le dataset.json
        json_path = None
        for root, dirs, files in os.walk(extracted_model_path):
            if "dataset.json" in files:
                json_path = os.path.abspath(os.path.join(root, "dataset.json"))
                break
        if not json_path:
            raise FileNotFoundError("dataset.json non trouvé")
        print(f"✅ dataset.json trouvé : {json_path}")

        # Charger le dataset.json
        with open(json_path, 'r') as f:
            dataset = json.load(f)

        # Supprimer la section training et mettre numTraining à 0
        dataset.pop("training", None)
        dataset["numTraining"] = 0

        # Lister les fichiers à tester
        image_filenames = sorted([
            f for f in os.listdir(input_path)
            if os.path.isfile(os.path.join(input_path, f)) and f.endswith('.nrrd')
        ])
        if not image_filenames:
            raise ValueError("Aucune image trouvée dans le dossier d'entrée.")

        # Créer le dossier imagesTs
        imagesTs_path = os.path.join(os.path.dirname(json_path), "imagesTs")
        os.makedirs(imagesTs_path, exist_ok=True)

        # Ajouter les nouvelles images test
        new_test_entries = []
        self.temp_copied_images = []

        for i, filename in enumerate(image_filenames, start=1):
            new_filename = f"{i:03d}_0000.nrrd"
            src = os.path.join(input_path, filename)
            dst = os.path.join(imagesTs_path, new_filename)
            shutil.copyfile(src, dst)
            print(f"\n 📂 Copié {filename} → imagesTs/{new_filename}")

            relative_path = f"./imagesTs/{new_filename}"
            new_test_entries.append([relative_path])
            self.temp_copied_images.append(dst)

        # Ajouter la section test
        dataset["numTest"] = len(image_filenames)
        dataset["test"] = new_test_entries

        # Sauvegarder
        with open(json_path, 'w') as f:
            json.dump(dataset, f, indent=4)

        # Stockage pour prédiction
        self.modified_dataset_json = json_path
        self.imagesTs_path = imagesTs_path


    def cleanup_temporary_test_images(self):
        for path in getattr(self, 'temporary_test_images', []):
            try:
                os.remove(path)
                print(f"🗑️ Fichier supprimé : {path}")
            except Exception as e:
                print(f"⚠️ Impossible de supprimer {path} : {e}")


    def onCheckBoxesChanged(self):
        if self.checkBoxParenchyma.checked:
            print("Segmenter parenchyme")
        if self.checkBoxAirways.checked:
            print("Segmenter voies aériennes")
        if self.checkBoxVascularTree.checked:
            print("Segmenter arbre vasculaire")