#!/usr/bin/env python3
"""
Train YOLOv8 on Basketball Detection Dataset

This script downloads a basketball-specific dataset from Roboflow and trains
YOLOv8 to detect basketballs more accurately than the generic COCO model.

Usage:
    python train_basketball_yolo.py

Requirements:
    pip install ultralytics roboflow
"""

import os
import sys
from pathlib import Path

# =============================================================================
# STEP 1: Install Dependencies
# =============================================================================
# Summary: Install ultralytics (YOLOv8) and roboflow packages for training.

def install_dependencies():
    """Install required packages if not present."""
    try:
        import ultralytics
        import roboflow
        print("✓ Dependencies already installed")
    except ImportError:
        print("Installing dependencies...")
        os.system("pip install ultralytics roboflow")
        print("✓ Dependencies installed")


def verify_gpu():
    """Verify GPU/MPS availability and print device info."""
    import torch

    print("\n" + "-"*40)
    print("GPU/DEVICE VERIFICATION")
    print("-"*40)
    print(f"PyTorch version: {torch.__version__}")

    if torch.cuda.is_available():
        print(f"✓ CUDA available: {torch.cuda.get_device_name(0)}")
        print(f"  CUDA version: {torch.version.cuda}")
        print(f"  GPU memory: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")
        return "cuda"
    elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
        print("✓ MPS (Apple Silicon) available")
        # Quick MPS test
        try:
            x = torch.randn(100, 100, device='mps')
            _ = x @ x
            torch.mps.synchronize()
            print("  MPS test: PASSED")
        except Exception as e:
            print(f"  MPS test: FAILED - {e}")
            return "cpu"
        return "mps"
    else:
        print("⚠ No GPU available, using CPU (training will be SLOW)")
        return "cpu"


# =============================================================================
# STEP 2: Download Dataset from Roboflow
# =============================================================================
# Summary: Download 5,386 labeled basketball images from Roboflow in YOLOv8 format.

def download_dataset(api_key: str = None, dataset_type: str = "ball_only"):
    """
    Download basketball detection datasets from Roboflow.

    Args:
        api_key: Your Roboflow API key (get free at roboflow.com)
        dataset_type: One of:
            - "ball_only": YOLOBball dataset (11k images, basketball only)
            - "ball_and_hoop": Combined datasets with ball + hoop detection
            - "reference": Same datasets as kylephan5/basketball-shot-tracker

    Returns:
        Path to the downloaded dataset
    """
    from roboflow import Roboflow

    if api_key is None:
        api_key = os.getenv("ROBOFLOW_API_KEY")
        if not api_key:
            print("\n" + "="*60)
            print("ROBOFLOW API KEY REQUIRED")
            print("="*60)
            print("1. Go to https://roboflow.com and create a free account")
            print("2. Go to Settings > API Key")
            print("3. Set your API key:")
            print("   export ROBOFLOW_API_KEY='your_key_here'")
            print("   OR pass it to this function")
            print("="*60 + "\n")
            sys.exit(1)

    print("Connecting to Roboflow...")
    rf = Roboflow(api_key=api_key)

    if dataset_type == "ball_only":
        # YOLOBball dataset - large basketball-only dataset
        print("Downloading YOLOBball dataset (11k images, ball only)...")
        project = rf.workspace("basketball-keumj").project("yolobball")
        dataset = project.version(3).download("yolov8")
        print(f"✓ Dataset downloaded to: {dataset.location}")
        return dataset.location

    elif dataset_type == "reference":
        # Same datasets used by kylephan5/basketball-shot-tracker
        # These include BOTH basketball AND hoop detection
        print("Downloading reference datasets (ball + hoop, ~600 images)...")

        # Dataset 1: basketball-lhqoe
        print("  Downloading dataset 1/2: basketball-lhqoe...")
        project1 = rf.workspace("034-ganesh-kumar-m-v-cs-r2lwe").project("basketball-lhqoe")
        ds1 = project1.version(1).download("yolov8")

        # Dataset 2: basketball-annotation-project
        print("  Downloading dataset 2/2: basketball-annotation-project...")
        project2 = rf.workspace("rodney-virtualassistant-gmail-com").project("basketball-annotation-project")
        ds2 = project2.version(2).download("yolov8")

        # Merge datasets
        merged_path = merge_datasets([ds1.location, ds2.location], "basketball_merged")
        print(f"✓ Merged dataset created at: {merged_path}")
        return merged_path

    elif dataset_type == "ball_and_hoop":
        # Combine YOLOBball (ball only) with a hoop dataset
        print("Downloading ball + hoop datasets...")

        # Large ball dataset
        print("  Downloading YOLOBball (ball detection)...")
        project1 = rf.workspace("basketball-keumj").project("yolobball")
        ds1 = project1.version(3).download("yolov8")

        # Hoop dataset from reference
        print("  Downloading hoop detection dataset...")
        project2 = rf.workspace("034-ganesh-kumar-m-v-cs-r2lwe").project("basketball-lhqoe")
        ds2 = project2.version(1).download("yolov8")

        merged_path = merge_datasets([ds1.location, ds2.location], "basketball_ball_and_hoop")
        print(f"✓ Merged dataset created at: {merged_path}")
        return merged_path

    else:
        raise ValueError(f"Unknown dataset_type: {dataset_type}")


def merge_datasets(dataset_paths: list, output_name: str):
    """
    Merge multiple YOLO datasets into one.

    Args:
        dataset_paths: List of paths to datasets (each with train/valid/test folders)
        output_name: Name for the merged dataset folder

    Returns:
        Path to merged dataset
    """
    import shutil
    import yaml

    output_path = Path(dataset_paths[0]).parent / output_name
    output_path.mkdir(exist_ok=True)

    # Create output structure
    for split in ["train", "valid", "test"]:
        (output_path / split / "images").mkdir(parents=True, exist_ok=True)
        (output_path / split / "labels").mkdir(parents=True, exist_ok=True)

    # Collect all class names
    all_classes = {}
    class_id_map = {}  # Maps (dataset_idx, old_id) -> new_id

    # First pass: collect all unique class names
    for ds_idx, ds_path in enumerate(dataset_paths):
        data_yaml = Path(ds_path) / "data.yaml"
        if data_yaml.exists():
            with open(data_yaml) as f:
                data = yaml.safe_load(f)
                names = data.get("names", [])
                if isinstance(names, dict):
                    names = [names[i] for i in sorted(names.keys())]
                for old_id, name in enumerate(names):
                    name_lower = name.lower().strip()
                    if name_lower not in all_classes:
                        new_id = len(all_classes)
                        all_classes[name_lower] = {"id": new_id, "name": name}
                    class_id_map[(ds_idx, old_id)] = all_classes[name_lower]["id"]

    print(f"  Merged classes: {[c['name'] for c in sorted(all_classes.values(), key=lambda x: x['id'])]}")

    # Second pass: copy and remap files
    file_count = 0
    for ds_idx, ds_path in enumerate(dataset_paths):
        ds_path = Path(ds_path)
        for split in ["train", "valid", "test"]:
            img_dir = ds_path / split / "images"
            lbl_dir = ds_path / split / "labels"

            if not img_dir.exists():
                continue

            for img_file in img_dir.iterdir():
                if img_file.suffix.lower() in [".jpg", ".jpeg", ".png", ".webp"]:
                    # Copy image with unique name
                    new_name = f"ds{ds_idx}_{img_file.name}"
                    shutil.copy(img_file, output_path / split / "images" / new_name)

                    # Copy and remap label
                    lbl_file = lbl_dir / f"{img_file.stem}.txt"
                    if lbl_file.exists():
                        with open(lbl_file) as f:
                            lines = f.readlines()

                        new_lines = []
                        for line in lines:
                            parts = line.strip().split()
                            if len(parts) >= 5:
                                old_class = int(parts[0])
                                new_class = class_id_map.get((ds_idx, old_class), old_class)
                                new_lines.append(f"{new_class} {' '.join(parts[1:])}\n")

                        with open(output_path / split / "labels" / f"ds{ds_idx}_{img_file.stem}.txt", "w") as f:
                            f.writelines(new_lines)

                    file_count += 1

    # Write merged data.yaml
    merged_yaml = {
        "path": str(output_path.absolute()),
        "train": "train/images",
        "val": "valid/images",
        "test": "test/images",
        "nc": len(all_classes),
        "names": [all_classes[k]["name"] for k in sorted(all_classes.keys(), key=lambda x: all_classes[x]["id"])]
    }

    with open(output_path / "data.yaml", "w") as f:
        yaml.dump(merged_yaml, f, default_flow_style=False)

    print(f"  Merged {file_count} images from {len(dataset_paths)} datasets")
    return str(output_path)


# =============================================================================
# STEP 3: Configure Training Parameters
# =============================================================================
# Summary: Set hyperparameters like epochs, batch size, and image size for optimal training.

def get_training_config(fast_mode: bool = True):
    """
    Return training configuration optimized for basketball detection.

    Args:
        fast_mode: If True, use optimizations for faster training (recommended for initial runs)
    """
    # Base config
    config = {
        # Model
        "model": "yolov8n.pt",  # Start with nano model (fast, good for mobile)

        # Training params
        "epochs": 100,          # Number of training epochs
        "patience": 20,         # Early stopping patience

        # Optimization
        "optimizer": "AdamW",   # AdamW often converges faster than Adam
        "lr0": 0.01,            # Higher initial LR with AdamW
        "lrf": 0.01,            # Final learning rate factor
        "cos_lr": True,         # Cosine learning rate scheduler

        # Augmentation (important for sports/motion)
        "hsv_h": 0.015,         # HSV-Hue augmentation
        "hsv_s": 0.7,           # HSV-Saturation augmentation
        "hsv_v": 0.4,           # HSV-Value augmentation
        "degrees": 10,          # Rotation augmentation
        "scale": 0.5,           # Scale augmentation
        "fliplr": 0.5,          # Horizontal flip probability

        # Device
        "device": "mps" if sys.platform == "darwin" else "0",  # MPS for Mac, GPU 0 otherwise
    }

    if fast_mode:
        # === SPEED OPTIMIZATIONS ===
        config.update({
            # Larger batch size - MPS can handle 32-64 with 16GB+ RAM
            "batch": 32,

            # Slightly smaller image size for faster processing
            "imgsz": 480,           # 480 is ~44% fewer pixels than 640, still good accuracy

            # Cache images in RAM for huge speedup (requires ~8GB RAM for this dataset)
            "cache": True,          # Set to "disk" if RAM is limited

            # Workers: 0 is often fastest on Mac due to MPS/multiprocessing issues
            "workers": 0,

            # Reduced augmentation for speed (still effective)
            "mosaic": 0.5,          # 50% mosaic instead of 100%
            "mixup": 0.0,           # Disable mixup (expensive, marginal benefit)

            # Close mosaic augmentation earlier
            "close_mosaic": 10,     # Disable mosaic for last 10 epochs

            # Reduce validation frequency
            "val": True,

            # Use automatic mixed precision (experimental on MPS, but can help)
            "amp": True,

            # Deterministic for reproducibility (slight speed cost, can disable)
            "deterministic": False,

            # Single class mode optimization
            "single_cls": False,    # Keep False since we only have 1 class anyway
        })
        print("⚡ Fast mode enabled: batch=32, imgsz=480, cache=True, workers=0")
    else:
        # Quality mode - slower but potentially better results
        config.update({
            "batch": 16,
            "imgsz": 640,
            "cache": True,
            "workers": 0,
            "mosaic": 1.0,
            "mixup": 0.1,
            "close_mosaic": 10,
            "amp": True,
        })
        print("🎯 Quality mode enabled: batch=16, imgsz=640, full augmentation")

    return config


# =============================================================================
# STEP 4: Train the Model
# =============================================================================
# Summary: Fine-tune YOLOv8 on the basketball dataset using transfer learning from COCO weights.

def train_model(dataset_path: str, config: dict):
    """
    Train YOLOv8 on the basketball dataset.

    Args:
        dataset_path: Path to downloaded dataset
        config: Training configuration dict

    Returns:
        Path to the best trained model
    """
    from ultralytics import YOLO

    # Load pre-trained model
    print(f"\nLoading base model: {config['model']}")
    model = YOLO(config["model"])

    # Find data.yaml in dataset
    data_yaml = Path(dataset_path) / "data.yaml"
    if not data_yaml.exists():
        # Try alternative locations
        for pattern in ["*/data.yaml", "data.yaml"]:
            matches = list(Path(dataset_path).glob(pattern))
            if matches:
                data_yaml = matches[0]
                break

    if not data_yaml.exists():
        raise FileNotFoundError(f"Could not find data.yaml in {dataset_path}")

    print(f"Using dataset config: {data_yaml}")

    # Train
    print("\n" + "="*60)
    print("STARTING TRAINING")
    print("="*60)
    print(f"Epochs: {config['epochs']}")
    print(f"Batch size: {config['batch']}")
    print(f"Image size: {config['imgsz']}")
    print(f"Device: {config['device']}")
    print(f"Cache: {config.get('cache', False)}")
    print(f"Workers: {config.get('workers', 'default')}")
    print(f"AMP (mixed precision): {config.get('amp', False)}")
    print(f"Mosaic: {config.get('mosaic', 1.0)}")
    print("="*60 + "\n")

    # Build training arguments from config
    train_args = {
        "data": str(data_yaml),
        "project": "basketball_detector",
        "name": "yolov8_basketball",
        "exist_ok": True,
    }

    # Add all config parameters
    for key, value in config.items():
        if key != "model":  # Skip model path, already loaded
            train_args[key] = value

    results = model.train(**train_args)

    # Get best model path
    best_model = Path("basketball_detector/yolov8_basketball/weights/best.pt")
    print(f"\n✓ Training complete!")
    print(f"✓ Best model saved to: {best_model}")

    return best_model


# =============================================================================
# STEP 5: Validate the Model
# =============================================================================
# Summary: Test the trained model on validation set to check accuracy metrics (mAP, precision, recall).

def validate_model(model_path: str, dataset_path: str):
    """Validate the trained model and print metrics."""
    from ultralytics import YOLO

    print("\n" + "="*60)
    print("VALIDATING MODEL")
    print("="*60)

    model = YOLO(model_path)

    data_yaml = Path(dataset_path) / "data.yaml"
    if not data_yaml.exists():
        for pattern in ["*/data.yaml", "data.yaml"]:
            matches = list(Path(dataset_path).glob(pattern))
            if matches:
                data_yaml = matches[0]
                break

    results = model.val(data=str(data_yaml))

    print("\n" + "="*60)
    print("VALIDATION RESULTS")
    print("="*60)
    print(f"mAP50:     {results.box.map50:.3f}")
    print(f"mAP50-95:  {results.box.map:.3f}")
    print(f"Precision: {results.box.mp:.3f}")
    print(f"Recall:    {results.box.mr:.3f}")
    print("="*60)

    return results


# =============================================================================
# STEP 6: Export Model for Production
# =============================================================================
# Summary: Copy the trained model to the project directory for use in the ball tracker.

def export_model(model_path: str, output_name: str = "basketball_detector.pt"):
    """Copy trained model to the core directory for use."""
    import shutil

    output_path = Path(__file__).parent / output_name
    shutil.copy(model_path, output_path)

    print(f"\n✓ Model exported to: {output_path}")
    print("\nTo use in BallTracker, update test_tracking.py:")
    print(f'  self.model = YOLO("{output_name}")')

    return output_path


# =============================================================================
# MAIN
# =============================================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Train YOLOv8 Basketball Detector")
    parser.add_argument("--quality", action="store_true",
                        help="Use quality mode (slower, full augmentation)")
    parser.add_argument("--dataset", type=str, default=None,
                        help="Path to existing dataset (skip download)")
    parser.add_argument("--dataset-type", type=str, default="ball_only",
                        choices=["ball_only", "ball_and_hoop", "reference"],
                        help="Dataset type: ball_only (11k images), ball_and_hoop (combined), reference (same as kylephan5 repo)")
    parser.add_argument("--batch", type=int, default=None,
                        help="Override batch size")
    parser.add_argument("--imgsz", type=int, default=None,
                        help="Override image size")
    parser.add_argument("--epochs", type=int, default=None,
                        help="Override number of epochs")
    parser.add_argument("--no-cache", action="store_true",
                        help="Disable image caching (if RAM is limited)")
    args = parser.parse_args()

    fast_mode = not args.quality

    print("\n" + "="*60)
    print("  YOLOv8 BASKETBALL DETECTOR TRAINING")
    print("="*60 + "\n")

    # Step 1: Install dependencies
    print("STEP 1: Checking dependencies...")
    install_dependencies()

    # Step 1.5: Verify GPU
    detected_device = verify_gpu()
    print("-"*40 + "\n")

    # Step 2: Download dataset or use provided path
    print("\nSTEP 2: Setting up dataset...")
    if args.dataset:
        dataset_path = args.dataset
        print(f"✓ Using provided dataset: {dataset_path}")
    else:
        print(f"Dataset type: {args.dataset_type}")
        dataset_path = download_dataset(dataset_type=args.dataset_type)

    # Step 3: Get training config
    print("\nSTEP 3: Configuring training parameters...")
    config = get_training_config(fast_mode=fast_mode)

    # Apply command-line overrides
    if args.batch:
        config["batch"] = args.batch
    if args.imgsz:
        config["imgsz"] = args.imgsz
    if args.epochs:
        config["epochs"] = args.epochs
    if args.no_cache:
        config["cache"] = False

    print(f"✓ Config loaded: {config['epochs']} epochs, batch={config['batch']}, imgsz={config['imgsz']}")

    # Step 4: Train
    print("\nSTEP 4: Training model...")
    model_path = train_model(dataset_path, config)

    # Step 5: Validate
    print("\nSTEP 5: Validating model...")
    validate_model(model_path, dataset_path)

    # Step 6: Export
    print("\nSTEP 6: Exporting model...")
    final_path = export_model(model_path)

    print("\n" + "="*60)
    print("  TRAINING COMPLETE!")
    print("="*60)
    print(f"\nYour basketball detector is ready at:")
    print(f"  {final_path}")
    print("\nNext steps:")
    print("  1. Update BallTracker to use 'basketball_detector.pt'")
    print("  2. Change ball_class from 32 to 0 (or check data.yaml)")
    print("  3. Test with: python test_tracking.py video.mp4 --debug-ball")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
