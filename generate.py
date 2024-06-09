from collections import OrderedDict
import json
import os
import sys
import argparse
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator


def extract_i18n_keys(html_content):
    soup = BeautifulSoup(html_content, "html.parser")
    i18n_dict = {}
    for tag in soup.find_all(attrs={"data-i18n": True}):
        i18n_values = str(tag.attrs.get("data-i18n")).split(";")

        for value in i18n_values:
            if value.startswith("["):
                end_bracket_pos = value.find("]")
                if end_bracket_pos != -1:
                    attribute_name = value[1:end_bracket_pos]
                    key = value[end_bracket_pos + 1 :]
                    value = tag.attrs.get(attribute_name, "")
                    i18n_dict[key] = value
            else:
                key = value
                value = tag.text.strip()
                i18n_dict[key] = value
    return i18n_dict


def process_html_files(directory):
    i18n_data = {}
    html_files = []
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith(".html"):
                filepath = os.path.join(root, file)
                html_files.append(filepath)
    html_files.sort()
    for html_file in html_files:
        with open(html_file, "r", encoding="utf-8") as f:
            html_content = f.read()
            i18n_data.update(extract_i18n_keys(html_content))
    return i18n_data


def update_json(
    json_file,
    i18n_dict,
    flags={"sort_keys": True, "auto_remove": True, "auto_add": True, "auto_translate": False},
):
    with open(json_file, "r", encoding="utf-8") as file:
        data = json.load(file, object_pairs_hook=OrderedDict)

    try:
        language = json_file.replace("\\", "/").split("/")[-1].split(".")[0]
        for key in i18n_dict.keys():
            if key not in data:
                print(f"Key '{key}' not found in '{json_file}'.")
                if i18n_dict[key] == "":
                    print(f"Skipping empty key '{key}'.")
                if flags["auto_add"] and i18n_dict[key] != "":
                    if flags["auto_translate"]:
                        try:
                            data[key] = GoogleTranslator(source="en", target=language).translate(i18n_dict[key])
                        except Exception as x:
                            if "No support for the provided language" in str(x):
                                language = language.split("-")[0]+'-'+language.split("-")[1].upper()
                                try:
                                    data[key] = GoogleTranslator(source="en", target=language).translate(i18n_dict[key])
                                except Exception as y:
                                    if "No support for the provided language" in str(y):
                                        language = language.split("-")[0]
                                        data[key] = GoogleTranslator(source="en", target=language).translate(i18n_dict[key])
                    else:
                        data[key] = i18n_dict[key]

    except Exception as e:
        print(f"Error processing '{json_file}': {e}", file=sys.stderr)

    for key in list(data.keys()):
        if key not in i18n_dict:
            print(f"{json_file} has extra key '{key}' not found in i18n dataset.")
            if flags["auto_remove"]:
                del data[key]

    # reorder keys as they appear in i18n dataset
    if flags["sort_keys"]:
        new_data = {}
        for key in i18n_dict.keys():
            if key in data:
                new_data[key] = data[key]
        data = new_data

    with open(json_file, "w", encoding="utf-8", newline="\n") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)
        file.write("\n")

    return data


if __name__ == "__main__":
    argparser = argparse.ArgumentParser(description="Update or Generate i18n JSON files")
    argparser.add_argument("json", help="JSON file path", type=str)
    argparser.add_argument("-d", "--directory", help="Directory path", type=str, default="./public")
    argparser.add_argument(
        "--auto-add",
        help="Auto add missing keys",
        action="store_true",
        default=True
    )
    argparser.add_argument(
        "--auto-translate",
        help="Auto translate missing keys when adding them",
        action="store_true",
        default=False,
    )
    argparser.add_argument(
        "--auto-remove",
        help="Auto remove extra keys",
        action="store_true",
        default=True,
    )
    argparser.add_argument(
        "--sort-keys",
        help="Sort keys as they appear in i18n dataset",
        action="store_true",
        default=False,
    )
    args = argparser.parse_args()
    json_file_path = args.json
    directory_path = args.directory

    if directory_path.endswith("/"):
        directory_path = directory_path[:-1]
    if directory_path.endswith("/locales"):
        directory_path = directory_path[:-8]
    if not os.path.exists(directory_path):
        print(f"Directory '{directory_path}' not found.", file=sys.stderr)
        exit(1)

    locales_path = os.path.join(directory_path, "locales")
    all_i18n_data = process_html_files(directory_path)
    flags = {
        "auto_add": args.auto_add,
        "auto_translate": args.auto_translate,
        "auto_remove": args.auto_remove,
        "sort_keys": args.sort_keys
    }

    if json_file_path:
        if not json_file_path.endswith(".json"):
            json_file_path = json_file_path + ".json"
        if not os.path.isabs(json_file_path):
            new_json_file_path = os.path.join(os.getcwd(), json_file_path)
            if os.path.exists(new_json_file_path):
                json_file_path = new_json_file_path
        if not os.path.exists(json_file_path):
            new_json_file_path = os.path.join(locales_path, json_file_path)
            if os.path.exists(new_json_file_path):
                json_file_path = new_json_file_path
            else:
                print(f"JSON file '{json_file_path}' not found.", file=sys.stderr)
                exit(1)
        updated_json = update_json(json_file_path, all_i18n_data, flags)
    else:
        print("Updating all JSON files...")
        for json_file in os.listdir(locales_path):
            if json_file.endswith(".json") and not json_file.endswith("lang.json") and not json_file.endswith("en.json"):
                json_file_path = os.path.join(locales_path, json_file)
                updated_json = update_json(json_file_path, all_i18n_data, flags)
    print("Done!")
