#!/usr/bin/env python3
"""
Prepare Rim Classifier Training Data from Roboflow Basketball Dataset

This script downloads the basketball-lhqoe dataset from Roboflow and prepares
rim-area crops for binary classification training to detect if a ball went through the hoop.

The dataset contains bounding boxes for "Basketball" and "Basketball Hoop" classes.
We extract crops around hoops and label them based on ball-hoop spatial relationships:
  - ball_through_hoop: ball overlaps hoop vertically AND ball center is at/below rim level
  - ball_not_through_hoop: all other cases (no ball near hoop, ball above hoop, etc.)

Output format: YOLOv8-cls directory structure
  rim_classifier_data/
    train/
      ball_through_hoop/
      ball_not_through_hoop/
    valid/
      ball_through_hoop/
      ball_not_through_hoop/

Usage:
    python prepare_rim_classifier_data.py --api-key YOUR_KEY
    python prepare_rim_classifier_data.py --output-dir /path/to/output

Requirements:
    pip install roboflow pillow pyyaml albumentations
"""

import os
import sys
import argparse
import shutil
from pathlib import Path
from collections import defaultdict
import yaml
from PIL import Image
import random

# Optional: albumentations for augmentation
try:
    import albumentations as A
    HAS_ALBUMENTATIONS = True
except ImportError:
    HAS_ALBUMENTATIONS = False
    print("Warning: albumentations not installed. Install with: pip install albumentations")
    print("Augmentation will be limited to basic PIL transforms.\n")


def download_dataset(api_key: str = None):
    """
    Download basketball-lhqoe dataset from Roboflow.

    Args:
        api_key: Roboflow API key

    Returns:
        Path to downloaded dataset
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
            print("   OR pass it via --api-key")
            print("="*60 + "\n")
            sys.exit(1)

    print("Connecting to Roboflow...")
    rf = Roboflow(api_key=api_key)

    print("Downloading basketball-lhqoe dataset...")
    project = rf.workspace("034-ganesh-kumar-m-v-cs-r2lwe").project("basketball-lhqoe")
    dataset = project.version(1).download("yolov8")

    print(f"✓ Dataset downloaded to: {dataset.location}")
    return dataset.location


def load_class_mapping(dataset_path: str):
    """
    Load class names from data.yaml to map class IDs to names.

    Args:
        dataset_path: Path to dataset

    Returns:
        dict: Mapping of class_id -> class_name
    """
    data_yaml = Path(dataset_path) / "data.yaml"
    if not data_yaml.exists():
        raise FileNotFoundError(f"data.yaml not found in {dataset_path}")

    with open(data_yaml) as f:
        data = yaml.safe_load(f)

    names = data.get("names", [])
    if isinstance(names, dict):
        # Already in {id: name} format
        class_map = {int(k): v for k, v in names.items()}
    else:
        # List format
        class_map = {i: name for i, name in enumerate(names)}

    print(f"Loaded class mapping: {class_map}")
    return class_map


def parse_yolo_label(label_path: str):
    """
    Parse YOLO format label file.

    Format: class_id center_x center_y width height (normalized 0-1)

    Returns:
        list of dicts with keys: class_id, cx, cy, w, h
    """
    if not os.path.exists(label_path):
        return []

    boxes = []
    with open(label_path) as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) >= 5:
                try:
                    boxes.append({
                        'class_id': int(parts[0]),
                        'cx': float(parts[1]),
                        'cy': float(parts[2]),
                        'w': float(parts[3]),
                        'h': float(parts[4])
                    })
                except ValueError:
                    continue
    return boxes


def boxes_overlap_vertically(ball_box, hoop_box, threshold=0.3):
    """
    Check if ball and hoop overlap in the horizontal (x) dimension.

    Args:
        ball_box: dict with cx, w
        hoop_box: dict with cx, w
        threshold: minimum overlap ratio (0-1)

    Returns:
        bool: True if they overlap horizontally
    """
    # Calculate x ranges
    ball_left = ball_box['cx'] - ball_box['w'] / 2
    ball_right = ball_box['cx'] + ball_box['w'] / 2
    hoop_left = hoop_box['cx'] - hoop_box['w'] / 2
    hoop_right = hoop_box['cx'] + hoop_box['w'] / 2

    # Calculate overlap
    overlap_left = max(ball_left, hoop_left)
    overlap_right = min(ball_right, hoop_right)
    overlap = max(0, overlap_right - overlap_left)

    # Normalize by smaller box width
    min_width = min(ball_box['w'], hoop_box['w'])
    if min_width == 0:
        return False

    overlap_ratio = overlap / min_width
    return overlap_ratio >= threshold


def is_ball_through_hoop(ball_box, hoop_box):
    """
    Determine if ball is going through the hoop based on spatial relationship.

    Criteria:
      1. Ball and hoop overlap horizontally (x-dimension)
      2. Ball center is at or below the hoop center (y >= cy_hoop)

    Args:
        ball_box: dict with cx, cy, w, h
        hoop_box: dict with cx, cy, w, h

    Returns:
        bool: True if ball appears to be going through hoop
    """
    # Check horizontal overlap
    if not boxes_overlap_vertically(ball_box, hoop_box, threshold=0.3):
        return False

    # Check if ball is at or below rim level
    # In image coordinates, y increases downward, so "below" means cy > hoop_cy
    ball_at_or_below_rim = ball_box['cy'] >= hoop_box['cy']

    return ball_at_or_below_rim


def crop_hoop_region(image_path: str, hoop_box: dict, expand_factor=2.0):
    """
    Crop expanded region around hoop bounding box.

    Args:
        image_path: Path to image
        hoop_box: dict with cx, cy, w, h (normalized 0-1)
        expand_factor: Factor to expand the crop region

    Returns:
        PIL.Image or None if crop fails
    """
    try:
        img = Image.open(image_path)
        img_w, img_h = img.size

        # Convert normalized coords to pixel coords
        cx = hoop_box['cx'] * img_w
        cy = hoop_box['cy'] * img_h
        w = hoop_box['w'] * img_w * expand_factor
        h = hoop_box['h'] * img_h * expand_factor

        # Calculate crop box (left, upper, right, lower)
        left = max(0, cx - w / 2)
        upper = max(0, cy - h / 2)
        right = min(img_w, cx + w / 2)
        lower = min(img_h, cy + h / 2)

        # Ensure valid crop
        if right <= left or lower <= upper:
            return None

        crop = img.crop((left, upper, right, lower))
        return crop

    except Exception as e:
        print(f"Warning: Failed to crop {image_path}: {e}")
        return None


def augment_image_basic(img):
    """
    Basic augmentation using PIL (fallback when albumentations not available).

    Returns:
        PIL.Image
    """
    import random
    from PIL import ImageEnhance

    # Horizontal flip (50% chance)
    if random.random() > 0.5:
        img = img.transpose(Image.FLIP_LEFT_RIGHT)

    # Brightness adjustment (±20%)
    if random.random() > 0.5:
        enhancer = ImageEnhance.Brightness(img)
        factor = random.uniform(0.8, 1.2)
        img = enhancer.enhance(factor)

    # Contrast adjustment (±20%)
    if random.random() > 0.5:
        enhancer = ImageEnhance.Contrast(img)
        factor = random.uniform(0.8, 1.2)
        img = enhancer.enhance(factor)

    # Slight rotation (±10 degrees)
    if random.random() > 0.5:
        angle = random.uniform(-10, 10)
        img = img.rotate(angle, fillcolor=(0, 0, 0))

    return img


def augment_image_albumentations(img):
    """
    Augmentation using albumentations library.

    Args:
        img: PIL.Image

    Returns:
        PIL.Image
    """
    import numpy as np

    # Convert PIL to numpy
    img_array = np.array(img)

    # Define augmentation pipeline
    transform = A.Compose([
        A.HorizontalFlip(p=0.5),
        A.RandomBrightnessContrast(brightness_limit=0.2, contrast_limit=0.2, p=0.5),
        A.HueSaturationValue(hue_shift_limit=10, sat_shift_limit=20, val_shift_limit=20, p=0.3),
        A.Rotate(limit=10, border_mode=0, p=0.5),
        A.GaussNoise(var_limit=(10.0, 30.0), p=0.2),
    ])

    augmented = transform(image=img_array)
    img_aug = Image.fromarray(augmented['image'])

    return img_aug


def process_dataset(dataset_path: str, output_dir: str, target_positive=100, target_negative=200):
    """
    Process dataset and create rim classifier training data.

    Args:
        dataset_path: Path to downloaded dataset
        output_dir: Output directory for classifier data
        target_positive: Target number of positive samples (ball_through_hoop)
        target_negative: Target number of negative samples (ball_not_through_hoop)
    """
    dataset_path = Path(dataset_path)
    output_dir = Path(output_dir)

    # Load class mapping
    class_map = load_class_mapping(dataset_path)

    # Find class IDs for basketball and hoop
    ball_class_id = None
    hoop_class_id = None

    for class_id, name in class_map.items():
        name_lower = name.lower()
        if 'basketball' in name_lower and 'hoop' not in name_lower:
            ball_class_id = class_id
        elif 'hoop' in name_lower or 'rim' in name_lower:
            hoop_class_id = class_id

    if ball_class_id is None or hoop_class_id is None:
        print(f"Error: Could not identify ball and hoop classes in {class_map}")
        sys.exit(1)

    print(f"Ball class ID: {ball_class_id} ({class_map[ball_class_id]})")
    print(f"Hoop class ID: {hoop_class_id} ({class_map[hoop_class_id]})")

    # Process each split (train, valid)
    stats = defaultdict(lambda: defaultdict(int))

    for split in ['train', 'valid']:
        print(f"\nProcessing {split} split...")

        img_dir = dataset_path / split / 'images'
        lbl_dir = dataset_path / split / 'labels'

        if not img_dir.exists():
            print(f"  Skipping {split} (directory not found)")
            continue

        # Create output directories
        pos_dir = output_dir / split / 'ball_through_hoop'
        neg_dir = output_dir / split / 'ball_not_through_hoop'
        pos_dir.mkdir(parents=True, exist_ok=True)
        neg_dir.mkdir(parents=True, exist_ok=True)

        # Collect samples
        positive_samples = []
        negative_samples = []

        for img_file in img_dir.iterdir():
            if img_file.suffix.lower() not in ['.jpg', '.jpeg', '.png', '.webp']:
                continue

            # Load corresponding label
            lbl_file = lbl_dir / f"{img_file.stem}.txt"
            boxes = parse_yolo_label(lbl_file)

            # Find hoops and balls
            hoops = [b for b in boxes if b['class_id'] == hoop_class_id]
            balls = [b for b in boxes if b['class_id'] == ball_class_id]

            # Skip images without hoops
            if not hoops:
                continue

            # Process each hoop
            for hoop_idx, hoop in enumerate(hoops):
                # Determine label based on ball-hoop relationship
                is_positive = False

                for ball in balls:
                    if is_ball_through_hoop(ball, hoop):
                        is_positive = True
                        break

                # Crop hoop region
                crop = crop_hoop_region(str(img_file), hoop, expand_factor=2.0)
                if crop is None:
                    continue

                # Add to appropriate list
                sample = {
                    'image': crop,
                    'source': f"{split}_{img_file.stem}_hoop{hoop_idx}"
                }

                if is_positive:
                    positive_samples.append(sample)
                else:
                    negative_samples.append(sample)

        print(f"  Found {len(positive_samples)} positive, {len(negative_samples)} negative samples")

        # Save samples
        for idx, sample in enumerate(positive_samples):
            filename = f"{sample['source']}.jpg"
            save_path = pos_dir / filename
            sample['image'].save(save_path)
            stats[split]['ball_through_hoop'] += 1

        for idx, sample in enumerate(negative_samples):
            filename = f"{sample['source']}.jpg"
            save_path = neg_dir / filename
            sample['image'].save(save_path)
            stats[split]['ball_not_through_hoop'] += 1

        # Augment minority class if needed
        if split == 'train':
            pos_count = stats[split]['ball_through_hoop']
            neg_count = stats[split]['ball_not_through_hoop']

            print(f"  Current counts: {pos_count} positive, {neg_count} negative")

            # Determine which class needs augmentation
            if pos_count < target_positive:
                print(f"  Augmenting positive class to reach {target_positive} samples...")
                augment_class(positive_samples, pos_dir, target_positive - pos_count)
                stats[split]['ball_through_hoop'] = target_positive

            if neg_count < target_negative:
                print(f"  Augmenting negative class to reach {target_negative} samples...")
                augment_class(negative_samples, neg_dir, target_negative - neg_count)
                stats[split]['ball_not_through_hoop'] = target_negative

    return stats


def augment_class(samples, output_dir, num_augmented):
    """
    Create augmented versions of samples.

    Args:
        samples: List of sample dicts with 'image' and 'source'
        output_dir: Directory to save augmented images
        num_augmented: Number of augmented samples to create
    """
    if not samples:
        print("    Warning: No samples to augment")
        return

    augment_fn = augment_image_albumentations if HAS_ALBUMENTATIONS else augment_image_basic

    for i in range(num_augmented):
        # Sample random image
        sample = random.choice(samples)

        # Augment
        img_aug = augment_fn(sample['image'])

        # Save with unique name
        filename = f"{sample['source']}_aug{i}.jpg"
        save_path = output_dir / filename
        img_aug.save(save_path)


def print_stats(stats):
    """Print dataset statistics."""
    print("\n" + "="*60)
    print("DATASET STATISTICS")
    print("="*60)

    for split in ['train', 'valid']:
        if split not in stats:
            continue

        print(f"\n{split.upper()}:")
        for class_name in ['ball_through_hoop', 'ball_not_through_hoop']:
            count = stats[split].get(class_name, 0)
            print(f"  {class_name}: {count}")

    print("\n" + "="*60)


def create_data_yaml(output_dir: str):
    """
    Create data.yaml for YOLOv8-cls format.

    Args:
        output_dir: Root directory of the dataset
    """
    output_dir = Path(output_dir)

    data = {
        'path': str(output_dir.absolute()),
        'train': 'train',
        'val': 'valid',
        'names': {
            0: 'ball_through_hoop',
            1: 'ball_not_through_hoop'
        },
        'nc': 2
    }

    yaml_path = output_dir / 'data.yaml'
    with open(yaml_path, 'w') as f:
        yaml.dump(data, f, default_flow_style=False)

    print(f"\n✓ Created data.yaml at {yaml_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Prepare rim classifier training data from Roboflow basketball dataset"
    )
    parser.add_argument(
        '--api-key',
        type=str,
        default=None,
        help='Roboflow API key (or set ROBOFLOW_API_KEY env var)'
    )
    parser.add_argument(
        '--output-dir',
        type=str,
        default='rim_classifier_data',
        help='Output directory for classifier data (default: rim_classifier_data)'
    )
    parser.add_argument(
        '--dataset-path',
        type=str,
        default=None,
        help='Path to existing downloaded dataset (skip download if provided)'
    )
    parser.add_argument(
        '--target-positive',
        type=int,
        default=100,
        help='Target number of positive samples (default: 100)'
    )
    parser.add_argument(
        '--target-negative',
        type=int,
        default=200,
        help='Target number of negative samples (default: 200)'
    )

    args = parser.parse_args()

    print("\n" + "="*60)
    print("  RIM CLASSIFIER DATA PREPARATION")
    print("="*60 + "\n")

    # Step 1: Download dataset (if not provided)
    if args.dataset_path:
        dataset_path = args.dataset_path
        print(f"Using existing dataset: {dataset_path}")
    else:
        print("Step 1: Downloading dataset from Roboflow...")
        dataset_path = download_dataset(api_key=args.api_key)

    # Step 2: Process dataset
    print("\nStep 2: Processing dataset and creating crops...")
    stats = process_dataset(
        dataset_path,
        args.output_dir,
        target_positive=args.target_positive,
        target_negative=args.target_negative
    )

    # Step 3: Create data.yaml
    print("\nStep 3: Creating data.yaml...")
    create_data_yaml(args.output_dir)

    # Step 4: Print statistics
    print_stats(stats)

    print("\n" + "="*60)
    print("  PREPARATION COMPLETE!")
    print("="*60)
    print(f"\nRim classifier data ready at: {Path(args.output_dir).absolute()}")
    print("\nNext steps:")
    print("  1. Review the generated crops to verify labeling quality")
    print("  2. Train classifier with: yolo classify train data=rim_classifier_data/data.yaml")
    print("  3. Or use your preferred classification framework (PyTorch, TensorFlow, etc.)")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
