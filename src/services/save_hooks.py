from pathlib import Path  # provides object-oriented file paths
def save_hooks(hooks, output_file):  # saves generated state or output files
    output_file = Path(output_file)

    output_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with open(output_file, "w", encoding="utf-8") as f:
        for idx, hook in enumerate(hooks, start=1):
            f.write(f"{idx}. {hook}\n")
