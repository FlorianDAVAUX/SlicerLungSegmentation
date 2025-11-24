if __name__ == "__main__":
    import argparse
    import sys
    import json
    from pathlib import Path
    from nnUNet_package.predict import run_nnunet_prediction
    from nnUNet_package import GLOBAL_CONTEXT

    parser = argparse.ArgumentParser()
    parser = argparse.ArgumentParser(description="nnUNetv2 Prediction Script")
    parser.add_argument("--mode", default="invivo", choices=["invivo", "exvivo", "axial"])
    parser.add_argument("--structure", required=True, choices=["parenchyma", "airways", "vascular", "parenchymaairways", "all", "lobes"])
    parser.add_argument("--input", required=True, help="Input image (.nii, .mha, .nrrd...)")
    parser.add_argument("--output", default="prediction", help="Output directory")
    parser.add_argument("--models_dir", required=True, help="Directory to store models")
    parser.add_argument("--animal", default="rabbit", choices=["rabbit", "pig"])
    parser.add_argument("--name", default="prediction", help="Final file name")
    parser.add_argument("--tmp_file", default=None, help="Temporary file to store the dataset json path")
    args = parser.parse_args()

    run_nnunet_prediction(
        mode=args.mode,
        structure=args.structure,
        input_path=args.input,
        output_dir=args.output,
        models_dir=args.models_dir,
        animal=args.animal,
    )

    # Save the dataset json path of the model in the temporary file
    with open(args.tmp_file, "w") as f:
        json.dump({"dataset_json_path": GLOBAL_CONTEXT.get("dataset_json_path")}, f)
