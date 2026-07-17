from pathlib import Path  # provides object-oriented file paths


SUPPORTED_FONT_EXTS = {".ttf", ".otf"}
def get_available_fonts(fonts_dir: str = "assets/fonts") -> list[str]:  # returns a resolved value used by later code
    folder = Path(fonts_dir)

    if not folder.exists():
        return ["Montserrat"]

    fonts = []

    for file in folder.rglob("*"):
        if file.is_file() and file.suffix.lower() in SUPPORTED_FONT_EXTS:
            name = file.stem

            # Clean common style suffixes
            for suffix in [
                "-Regular",
                "-Bold",
                "-Italic",
                "-Medium",
                "-SemiBold",
                "-ExtraBold",
                "-Black",
                "-Light",
                "-Thin",
                "-VariableFont_wght",
                "-Italic-VariableFont_wght",
            ]:
                name = name.replace(suffix, "")

            pretty_names = {
                "BebasNeue": "Bebas Neue",
                "ArchivoBlack": "Archivo Black",
                "LuckiestGuy": "Luckiest Guy",
            }
            fonts.append(pretty_names.get(name, name))

    fonts = sorted(set(fonts))

    return fonts or ["Montserrat"]
