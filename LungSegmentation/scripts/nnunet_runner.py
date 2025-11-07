if __name__ == "__main__":
    import argparse
    import sys
    import json
    from pathlib import Path
    from nnUNet_package.predict import run_nnunet_prediction
    from nnUNet_package import GLOBAL_CONTEXT

    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True, help="Mode de segmentation (Invivo, Exvivo, Axial)")
    parser.add_argument("--structure", required=True, help="Structure à segmenter")
    parser.add_argument("--input", required=True, help="Chemin vers le fichier d'entrée")
    parser.add_argument("--output", required=True, help="Répertoire de sortie pour les résultats")
    parser.add_argument("--models_dir", required=True, help="Répertoire contenant les modèles")
    parser.add_argument("--animal", default="rabbit", help="Nom de l'animal")
    parser.add_argument("--tmp_file", default=None, help="Fichier temporaire pour stocker le chemin du dataset json")
    args = parser.parse_args()

    run_nnunet_prediction(
        mode=args.mode,
        structure=args.structure,
        input_path=args.input,
        output_dir=args.output,
        models_dir=args.models_dir,
        animal=args.animal,
    )

    # Sauvegarde le chemin du dataset json du modèle dans le fichier temporaire
    with open(args.tmp_file, "w") as f:
        json.dump({"dataset_json_path": GLOBAL_CONTEXT.get("dataset_json_path")}, f)
