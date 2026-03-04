import json
import os
import subprocess
import re
import concurrent.futures

ALAJA_PATH = "/home/lorenzosnchez/proyectos/alaja/alaja"

def _call_alaja(hex_color, mode, amount):
    # Map amount [0, 1] to [1, 10]
    alaja_amount = max(1, min(10, round(amount * 10)))
    cmd = [ALAJA_PATH, "--color", hex_color, f"--{mode}", str(alaja_amount), "--raw"]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        try:
            data = json.loads(result.stdout)
            return data["base"]["hex"]
        except json.JSONDecodeError:
            print(f"Failed to parse Alaja output: {result.stdout}")
    else:
        print(f"Alaja failed: {result.stderr}")
    
    return hex_color

def get_harmony(hex_color, harmony_type):
    cmd = [ALAJA_PATH, "--harmony", harmony_type, "--color", hex_color, "--raw"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        try:
            data = json.loads(result.stdout)
            return [c["hex"] for c in data.get("harmonies", {}).get("colors", [])]
        except json.JSONDecodeError:
            pass
    return []

def darken(hex_color, amount=0.2):
    return _call_alaja(hex_color, "darken", amount)

def lighten(hex_color, amount=0.2):
    return _call_alaja(hex_color, "lighten", amount)

def generate_theme(name, base_colors, variant_type, display_name):
    # The user requested to base the themes entirely on the "selection" field
    base_hex = base_colors['selection']
    
    # Calculate harmonies dynamically using Alaja (now works correctly using regex parsing)
    analogous = get_harmony(base_hex, "analogous")
    triad = get_harmony(base_hex, "triad")
    complementary = get_harmony(base_hex, "complementary")
    split = get_harmony(base_hex, "split_complementary")
    square = get_harmony(base_hex, "square")

    sel = base_hex
    key = base_hex  # Make keywords and primary accent match the actual hue
    
    def safe_get(colors_list, index, fallback):
        return colors_list[index] if len(colors_list) > index else fallback

    # Meaningful harmonic pairings for code tokens to create variety
    str_col = safe_get(analogous, 1, base_hex)
    func_col = safe_get(triad, 1, base_hex)
    num_col = safe_get(complementary, 1, safe_get(split, 1, base_hex))
    class_col = safe_get(square, 1, func_col)
    type_col = safe_get(square, 2, class_col)
    param_col = safe_get(analogous, 2, str_col)
    prop_col = safe_get(split, 2, base_hex)
    regex_col = safe_get(triad, 2, str_col)

    if variant_type == 'light':
        type_str = "light"
        bg = base_colors['background'] # Keep the visually pleasing tinted bg
        fg = darken(base_hex, 0.8)
        com = darken(base_hex, 0.4)
        
        # Fix unreadable yellow strings in orange light theme
        if name == "orange":
            str_col = darken(str_col, 0.5)

    elif variant_type == 'dark':
        type_str = "dark"
        bg = base_colors['background'] # Keep the visually pleasing tinted dark bg
        fg = lighten(base_hex, 0.8)
        com = darken(base_hex, 0.2)
    elif variant_type == 'deep':
        type_str = "dark"
        # Purely generated "deep" background based heavily on the selection color for max vibrancy
        bg = darken(base_hex, 0.85) 
        fg = lighten(base_hex, 0.7)
        com = darken(base_hex, 0.2)

    theme = {
        "name": display_name,
        "type": type_str,
        "colors": {
            "editor.background": bg,
            "editor.foreground": fg,
            "editor.selectionBackground": sel + "80",
            "editor.lineHighlightBackground": darken(bg, 0.05) if type_str == "dark" else lighten(bg, 0.05),
            "editorCursor.foreground": key,
            "editorWhitespace.foreground": com + "40",
            "editorIndentGuide.background": com + "20",
            "editorIndentGuide.activeBackground": key + "60",
            
            # Workbench
            "activityBar.background": bg,
            "activityBar.foreground": fg,
            "activityBar.inactiveForeground": fg + "60",
            "activityBarBadge.background": key,
            "activityBarBadge.foreground": bg,
            
            "sideBar.background": darken(bg, 0.1) if type_str == "dark" else lighten(bg, 0.1),
            "sideBar.foreground": fg,
            "sideBarSectionHeader.background": bg,
            
            "statusBar.background": key,
            "statusBar.foreground": bg,
            "statusBar.noFolderBackground": key,
            
            "titleBar.activeBackground": bg,
            "titleBar.activeForeground": fg,
            
            "tab.activeBackground": bg,
            "tab.activeForeground": fg,
            "tab.inactiveBackground": darken(bg, 0.05),
            "tab.inactiveForeground": fg + "80",
            
            "terminal.background": bg,
            "terminal.foreground": fg,
        },
        "tokenColors": [
            { "scope": "comment", "settings": { "foreground": com } },
            { "scope": "string", "settings": { "foreground": str_col } },
            { "scope": "string.regexp", "settings": { "foreground": regex_col } },
            { "scope": "constant.numeric", "settings": { "foreground": num_col } },
            { "scope": "constant.language", "settings": { "foreground": num_col, "fontStyle": "italic" } },
            { "scope": "keyword", "settings": { "foreground": key, "fontStyle": "bold" } },
            { "scope": "storage", "settings": { "foreground": key } },
            { "scope": "storage.type", "settings": { "foreground": type_col, "fontStyle": "italic" } },
            { "scope": "entity.name.function", "settings": { "foreground": func_col } },
            { "scope": "entity.name.class", "settings": { "foreground": class_col, "fontStyle": "bold" } },
            { "scope": "entity.name.type", "settings": { "foreground": type_col } },
            { "scope": "variable", "settings": { "foreground": fg } },
            { "scope": "variable.parameter", "settings": { "foreground": param_col, "fontStyle": "italic" } },
            { "scope": "variable.other.property", "settings": { "foreground": prop_col } },
            { "scope": "punctuation", "settings": { "foreground": fg + "B0" } }
        ]
    }
    return theme


def main():
    # Get the directory where the script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    input_file = os.path.join(script_dir, 'Themixir.json')
    output_dir = os.path.join(script_dir, 'themes')
    package_json_path = os.path.join(script_dir, 'package.json')
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    with open(input_file, 'r') as f:
        data = json.load(f)

    def make_themes_for_color(item):
        color_name, content = item
        # Themixir Red -> Red
        pure_name = color_name.replace("Themixir ", "")
        safe_name = pure_name.lower().replace(" ", "_")
        
        # Variants from JSON
        dark_key = f"themixir_{safe_name}_dark"
        light_key = f"themixir_{safe_name}_light"
        
        variants = [
            ('light', light_key, f"Themixir {pure_name} Light"),
            ('dark', dark_key, f"Themixir {pure_name} Dark"),
            ('deep', dark_key, f"Themixir {pure_name} Deep") # Deep uses Dark settings as base
        ]

        themes_added = []
        for v_type, v_key, display in variants:
            if v_key in content:
                base = content[v_key]
                theme_json = generate_theme(safe_name, base, v_type, display)
                
                filename = f"{safe_name}_{v_type}.json"
                filepath = os.path.join(output_dir, filename)
                
                with open(filepath, 'w') as tf:
                    json.dump(theme_json, tf, indent=2)
                
                themes_added.append({
                    "label": display,
                    "uiTheme": "vs" if v_type == 'light' else "vs-dark",
                    "path": f"./themes/{filename}"
                })
        return themes_added

    manifest_themes = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        for result in executor.map(make_themes_for_color, data.items()):
            manifest_themes.extend(result)

    # Update package.json
    pkg = {
        "name": "themixir-themes",
        "displayName": "Themixir! Elixir Themes for VS Code (and Cursor, and Antigravity, and all the folks)",
        "description": "A collection of 30 vibrant themes based on custom color palettes.",
        "version": "1.0.2",
        "publisher": "Lorenzo-SF",
        "repository": {
            "type": "git",
            "url": "https://github.com/lorenzo-sf/themixir"
        },
        "license": "SEE LICENSE IN LICENSE",
        "icon": "themixir_icon.png",
        "engines": { "vscode": "^1.50.0" },
        "categories": ["Themes"],
        "contributes": {
            "themes": manifest_themes
        }
    }
    
    with open(package_json_path, 'w') as pf:
        json.dump(pkg, pf, indent=2)

    print(f"Generated {len(manifest_themes)} themes and updated package.json")

if __name__ == "__main__":
    main()
