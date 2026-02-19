from collections import OrderedDict
import argparse
import json
import os
import re
import sys
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator


SOURCE_EXTENSIONS = (".html", ".js", ".mjs", ".cjs", ".ts", ".tsx")
EXCLUDED_SEGMENTS = {
    ".git",
    "node_modules",
    "dist",
    "build",
    "coverage",
    "__pycache__",
}
EXCLUDED_PATH_PREFIXES = (
    "plugins/",
    "public/plugins/",
    "user/plugins/",
    "extensions/third-party/",
    "scripts/extensions/third-party/",
    "public/scripts/extensions/third-party/",
)


COLOR_CODES = {
    "red": "31",
    "green": "32",
    "yellow": "33",
    "blue": "34",
    "magenta": "35",
    "cyan": "36",
    "gray": "90",
}


def supports_color(stream):
    if os.getenv("NO_COLOR"):
        return False
    if os.getenv("TERM", "").lower() == "dumb":
        return False
    return hasattr(stream, "isatty") and stream.isatty()


def colorize(text, color_name, stream):
    if not supports_color(stream):
        return text
    color_code = COLOR_CODES.get(color_name, "")
    if not color_code:
        return text
    return f"\033[{color_code}m{text}\033[0m"


def print_status(tag, message, color="cyan", stream=sys.stdout):
    normalized_tag = f"{str(tag).upper():>3}"
    colored_tag = colorize(normalized_tag, color, stream)
    print(f"[{colored_tag}] {message}", file=stream)


def format_display_path(path):
    normalized = path.replace("\\", "/")
    try:
        relative = os.path.relpath(path, os.getcwd()).replace("\\", "/")
        if not relative.startswith("."):
            relative = f"./{relative}"
        return relative
    except Exception:
        return normalized


def create_run_totals():
    return {
        "files": 0,
        "nf": 0,
        "add": 0,
        "skip": 0,
        "dup": 0,
        "extra": 0,
        "remove": 0,
        "err": 0,
    }


def normalize_relative_path(path, base_directory):
    relative_path = os.path.relpath(path, base_directory)
    return relative_path.replace("\\", "/").lstrip("./").lower()


def should_skip_path(path, base_directory):
    relative_path = normalize_relative_path(path, base_directory)
    if relative_path in ("", "."):
        return False

    path_segments = [segment for segment in relative_path.split("/") if segment]
    if any(segment in EXCLUDED_SEGMENTS for segment in path_segments):
        return True

    for prefix in EXCLUDED_PATH_PREFIXES:
        normalized_prefix = prefix.rstrip("/")
        if relative_path == normalized_prefix or relative_path.startswith(prefix):
            return True
    return False


def merge_i18n_entries(target, source):
    for key, value in source.items():
        if not key:
            continue
        if key not in target:
            target[key] = value
        elif target[key] == "" and value != "":
            target[key] = value


def load_json_with_first_key_wins(json_file):
    duplicate_keys = []

    def object_pairs_first_wins(pairs):
        data = OrderedDict()
        for key, value in pairs:
            if key in data:
                duplicate_keys.append(key)
                continue
            data[key] = value
        return data

    with open(json_file, "r", encoding="utf-8") as file:
        content = file.read()

    parsed_data = json.loads(content, object_pairs_hook=object_pairs_first_wins)
    return parsed_data, duplicate_keys


def extract_i18n_keys_from_html(html_content):
    soup = BeautifulSoup(html_content, "html.parser")
    i18n_dict = OrderedDict()

    for tag in soup.find_all(attrs={"data-i18n": True}):
        i18n_values = str(tag.attrs.get("data-i18n")).split(";")
        for i18n_value in i18n_values:
            token = str(i18n_value)
            if token == "":
                continue

            if token.startswith("["):
                end_bracket_pos = token.find("]")
                if end_bracket_pos != -1:
                    attribute_name = token[1:end_bracket_pos]
                    key = token[end_bracket_pos + 1 :]
                    value = str(tag.attrs.get(attribute_name, "")).strip()
                    if key != "":
                        i18n_dict[key] = value
            else:
                key = token
                value = tag.text.strip()
                if key != "":
                    i18n_dict[key] = value

    return i18n_dict


def extract_i18n_keys_from_data_i18n_value(data_i18n_value):
    i18n_dict = OrderedDict()
    if data_i18n_value is None:
        return i18n_dict

    for raw_token in str(data_i18n_value).split(";"):
        token = str(raw_token)
        if token == "":
            continue
        if token.startswith("["):
            end_bracket_pos = token.find("]")
            if end_bracket_pos != -1:
                key = token[end_bracket_pos + 1 :]
                if key != "":
                    i18n_dict[key] = key
            continue
        i18n_dict[token] = token
    return i18n_dict


def extract_i18n_keys_from_markup_text(markup_text):
    i18n_dict = OrderedDict()
    if not markup_text or "data-i18n" not in markup_text:
        return i18n_dict

    merge_i18n_entries(i18n_dict, extract_i18n_keys_from_html(markup_text))

    # Handle HTML fragments that are not valid standalone tags but still contain data-i18n attributes.
    for match in re.finditer(r'data-i18n\s*=\s*(["\'])(.*?)\1', markup_text, flags=re.IGNORECASE | re.DOTALL):
        merge_i18n_entries(i18n_dict, extract_i18n_keys_from_data_i18n_value(match.group(2)))

    return i18n_dict


def is_identifier_char(char):
    return bool(char) and (char.isalnum() or char in "_$")


def decode_js_escape(source, index):
    if index >= len(source):
        return "\\", index

    escape_char = source[index]
    simple_escapes = {
        "b": "\b",
        "f": "\f",
        "n": "\n",
        "r": "\r",
        "t": "\t",
        "v": "\v",
        "0": "\0",
        "\\": "\\",
        "'": "'",
        '"': '"',
        "`": "`",
        "$": "$",
    }
    if escape_char in simple_escapes:
        return simple_escapes[escape_char], index + 1

    if escape_char == "x" and index + 2 < len(source):
        hex_value = source[index + 1 : index + 3]
        if all(char in "0123456789abcdefABCDEF" for char in hex_value):
            return chr(int(hex_value, 16)), index + 3

    if escape_char == "u":
        if index + 1 < len(source) and source[index + 1] == "{":
            close_pos = source.find("}", index + 2)
            if close_pos != -1:
                hex_value = source[index + 2 : close_pos]
                if hex_value and all(char in "0123456789abcdefABCDEF" for char in hex_value):
                    return chr(int(hex_value, 16)), close_pos + 1
        elif index + 4 < len(source):
            hex_value = source[index + 1 : index + 5]
            if all(char in "0123456789abcdefABCDEF" for char in hex_value):
                return chr(int(hex_value, 16)), index + 5

    return escape_char, index + 1


def skip_string_literal(source, start_index):
    quote = source[start_index]
    index = start_index + 1

    while index < len(source):
        char = source[index]
        if char == "\\":
            _, index = decode_js_escape(source, index + 1)
            continue
        if char == quote:
            return index + 1
        index += 1
    return len(source)


def skip_line_comment(source, start_index):
    newline_pos = source.find("\n", start_index)
    return len(source) if newline_pos == -1 else newline_pos + 1


def skip_block_comment(source, start_index):
    comment_end = source.find("*/", start_index + 2)
    return len(source) if comment_end == -1 else comment_end + 2


def find_previous_significant_char(source, start_index):
    index = start_index - 1
    while index >= 0 and source[index].isspace():
        index -= 1
    return source[index] if index >= 0 else ""


def can_start_regex_literal(source, start_index):
    previous_char = find_previous_significant_char(source, start_index)
    if previous_char == "":
        return True
    return previous_char in "({[,:;=!?&|^~<>+-*%"


def skip_regex_literal(source, start_index):
    index = start_index + 1
    in_char_class = False

    while index < len(source):
        char = source[index]

        if char == "\\":
            index += 2
            continue
        if char == "[" and not in_char_class:
            in_char_class = True
            index += 1
            continue
        if char == "]" and in_char_class:
            in_char_class = False
            index += 1
            continue
        if char == "/" and not in_char_class:
            index += 1
            while index < len(source) and source[index].isalpha():
                index += 1
            return index
        if char in "\n\r":
            # Abort on malformed regex; treat '/' as a regular char.
            return start_index + 1
        index += 1

    return len(source)


def consume_js_expression(source, start_index):
    index = start_index
    brace_depth = 1

    while index < len(source):
        char = source[index]
        next_char = source[index + 1] if index + 1 < len(source) else ""

        if char in ("'", '"'):
            index = skip_string_literal(source, index)
            continue
        if char == "`":
            index = skip_template_literal(source, index)
            continue
        if char == "/" and next_char == "/":
            index = skip_line_comment(source, index)
            continue
        if char == "/" and next_char == "*":
            index = skip_block_comment(source, index)
            continue
        if char == "/" and can_start_regex_literal(source, index):
            index = skip_regex_literal(source, index)
            continue
        if char == "{":
            brace_depth += 1
            index += 1
            continue
        if char == "}":
            brace_depth -= 1
            index += 1
            if brace_depth == 0:
                return index
            continue
        index += 1

    return len(source)


def consume_template_literal_with_interpolations(source, start_index, replace_interpolations=False):
    index = start_index + 1
    text_buffer = []
    placeholder_index = 0
    has_interpolation = False
    interpolation_ranges = []

    while index < len(source):
        char = source[index]
        next_char = source[index + 1] if index + 1 < len(source) else ""

        if char == "\\":
            decoded, index = decode_js_escape(source, index + 1)
            text_buffer.append(decoded)
            continue

        if char == "`":
            return index + 1, "".join(text_buffer), has_interpolation, True, interpolation_ranges

        if char == "$" and next_char == "{":
            has_interpolation = True
            expression_start = index + 2
            expression_end = consume_js_expression(source, expression_start)
            if expression_end - 1 > expression_start:
                interpolation_ranges.append((expression_start, expression_end - 1))
            if replace_interpolations:
                text_buffer.append(f"${{{placeholder_index}}}")
                placeholder_index += 1
            index = expression_end
            continue

        text_buffer.append(char)
        index += 1

    return len(source), "".join(text_buffer), has_interpolation, False, interpolation_ranges


def consume_template_literal(source, start_index, replace_interpolations=False):
    next_index, parsed_text, has_interpolation, complete, _ = consume_template_literal_with_interpolations(
        source, start_index, replace_interpolations=replace_interpolations
    )
    return next_index, parsed_text, has_interpolation, complete


def skip_template_literal(source, start_index):
    next_index, _, _, _ = consume_template_literal(source, start_index, replace_interpolations=False)
    return next_index


def parse_js_string_literal(value):
    stripped = value.strip()
    if len(stripped) < 2 or stripped[0] not in ("'", '"'):
        return None

    quote = stripped[0]
    index = 1
    decoded_chars = []

    while index < len(stripped):
        char = stripped[index]
        if char == "\\":
            decoded, index = decode_js_escape(stripped, index + 1)
            decoded_chars.append(decoded)
            continue
        if char == quote:
            tail = stripped[index + 1 :].strip()
            if tail:
                return None
            return "".join(decoded_chars)
        decoded_chars.append(char)
        index += 1

    return None


def parse_static_js_value(value):
    string_value = parse_js_string_literal(value)
    if string_value is not None:
        return string_value

    stripped = value.strip()
    if not stripped or stripped[0] != "`":
        return None

    end_index, parsed_text, has_interpolation, complete = consume_template_literal(
        stripped, 0, replace_interpolations=False
    )
    if not complete or end_index != len(stripped) or has_interpolation:
        return None
    return parsed_text


def parse_js_call_arguments(source, open_paren_index):
    index = open_paren_index + 1
    arg_start = index
    paren_depth = 1
    brace_depth = 0
    bracket_depth = 0
    arguments = []

    while index < len(source):
        char = source[index]
        next_char = source[index + 1] if index + 1 < len(source) else ""

        if char in ("'", '"'):
            index = skip_string_literal(source, index)
            continue
        if char == "`":
            index = skip_template_literal(source, index)
            continue
        if char == "/" and next_char == "/":
            index = skip_line_comment(source, index)
            continue
        if char == "/" and next_char == "*":
            index = skip_block_comment(source, index)
            continue
        if char == "/" and can_start_regex_literal(source, index):
            index = skip_regex_literal(source, index)
            continue
        if char == "(":
            paren_depth += 1
            index += 1
            continue
        if char == ")":
            paren_depth -= 1
            if paren_depth == 0:
                arguments.append(source[arg_start:index])
                return index + 1, arguments
            index += 1
            continue
        if char == "{":
            brace_depth += 1
            index += 1
            continue
        if char == "}":
            brace_depth = max(0, brace_depth - 1)
            index += 1
            continue
        if char == "[":
            bracket_depth += 1
            index += 1
            continue
        if char == "]":
            bracket_depth = max(0, bracket_depth - 1)
            index += 1
            continue
        if char == "," and paren_depth == 1 and brace_depth == 0 and bracket_depth == 0:
            arguments.append(source[arg_start:index])
            arg_start = index + 1
            index += 1
            continue
        index += 1

    return len(source), None


def parse_js_assignment_expression(source, start_index):
    index = start_index
    paren_depth = 0
    brace_depth = 0
    bracket_depth = 0

    while index < len(source):
        char = source[index]
        next_char = source[index + 1] if index + 1 < len(source) else ""

        if char in ("'", '"'):
            index = skip_string_literal(source, index)
            continue
        if char == "`":
            index = skip_template_literal(source, index)
            continue
        if char == "/" and next_char == "/":
            index = skip_line_comment(source, index)
            continue
        if char == "/" and next_char == "*":
            index = skip_block_comment(source, index)
            continue
        if char == "/" and can_start_regex_literal(source, index):
            index = skip_regex_literal(source, index)
            continue
        if char == "(":
            paren_depth += 1
            index += 1
            continue
        if char == ")":
            paren_depth = max(0, paren_depth - 1)
            index += 1
            continue
        if char == "{":
            brace_depth += 1
            index += 1
            continue
        if char == "}":
            brace_depth = max(0, brace_depth - 1)
            index += 1
            continue
        if char == "[":
            bracket_depth += 1
            index += 1
            continue
        if char == "]":
            bracket_depth = max(0, bracket_depth - 1)
            index += 1
            continue
        if char == ";" and paren_depth == 0 and brace_depth == 0 and bracket_depth == 0:
            return index + 1, source[start_index:index]
        index += 1

    return len(source), source[start_index:]


def has_translation_t_call_binding(script_content):
    module_hint = r"[^\"'\n]*(?:i18n|locale|l10n|translation|translator)[^\"'\n]*"
    binding_patterns = (
        rf"\bimport\s*\{{[^}}]*\bt\b[^}}]*\}}\s*from\s*([\"']){module_hint}\1",
        rf"\bimport\s+t\s+from\s*([\"']){module_hint}\1",
        r"\b(?:const|let|var)\s*\{[^}]*\bt\b[^}]*\}\s*=\s*(?:i18n|i18next|locale|translator|translation)\b",
        r"\b(?:const|let|var)\s+t\s*=\s*(?:translate|i18n\.t|window\.t)\b",
        r"\bthis\.t\s*=\s*(?:translate|i18n\.t|window\.t)\b",
    )
    for pattern in binding_patterns:
        if re.search(pattern, script_content):
            return True
    return False


def is_noise_t_call_key(candidate_text):
    text = candidate_text.strip()
    if text == "":
        return True
    if text.startswith(("./", "../", "/", "?")):
        return True
    if "node_modules/" in text or "/src/" in text or "dist/" in text:
        return True
    if "<" in text or ">" in text:
        return True
    if re.search(r"\.(?:js|mjs|cjs|wasm|json|ts|tsx)(?:\?|$)", text, flags=re.IGNORECASE):
        return True
    if re.fullmatch(r"\?[0-9a-f]{3,}", text, flags=re.IGNORECASE):
        return True
    return False


def extract_i18n_keys_from_scripts(script_content):
    i18n_dict = OrderedDict()
    index = 0
    allow_t_function_call_extraction = has_translation_t_call_binding(script_content)

    while index < len(script_content):
        char = script_content[index]
        next_char = script_content[index + 1] if index + 1 < len(script_content) else ""

        if char == "/" and next_char == "/":
            index = skip_line_comment(script_content, index)
            continue
        if char == "/" and next_char == "*":
            index = skip_block_comment(script_content, index)
            continue
        if char in ("'", '"'):
            next_index = skip_string_literal(script_content, index)
            string_value = parse_js_string_literal(script_content[index:next_index])
            if string_value and "data-i18n" in string_value:
                merge_i18n_entries(i18n_dict, extract_i18n_keys_from_markup_text(string_value))
            index = next_index
            continue
        if char == "`":
            next_index, parsed_text, _, complete, interpolation_ranges = consume_template_literal_with_interpolations(
                script_content, index, replace_interpolations=True
            )
            if complete and "data-i18n" in parsed_text:
                merge_i18n_entries(i18n_dict, extract_i18n_keys_from_markup_text(parsed_text))
            for interpolation_start, interpolation_end in interpolation_ranges:
                interpolation_content = script_content[interpolation_start:interpolation_end]
                if interpolation_content:
                    merge_i18n_entries(i18n_dict, extract_i18n_keys_from_scripts(interpolation_content))
            index = next_index
            continue
        if char == "/" and can_start_regex_literal(script_content, index):
            index = skip_regex_literal(script_content, index)
            continue

        if script_content.startswith("t", index):
            previous_char = script_content[index - 1] if index > 0 else ""
            if not is_identifier_char(previous_char) and previous_char != ".":
                if index + 1 >= len(script_content) or not is_identifier_char(script_content[index + 1]):
                    whitespace_index = index + 1
                    while whitespace_index < len(script_content) and script_content[whitespace_index].isspace():
                        whitespace_index += 1
                    if whitespace_index < len(script_content) and script_content[whitespace_index] == "`":
                        next_index, parsed_text, _, complete = consume_template_literal(
                            script_content, whitespace_index, replace_interpolations=True
                        )
                        if complete and parsed_text:
                            i18n_dict[parsed_text] = parsed_text
                        index = next_index
                        continue
                    if (
                        allow_t_function_call_extraction
                        and whitespace_index < len(script_content)
                        and script_content[whitespace_index] == "("
                    ):
                        next_index, arguments = parse_js_call_arguments(script_content, whitespace_index)
                        if arguments:
                            text_value = parse_static_js_value(arguments[0]) if len(arguments) > 0 else None
                            if text_value and not is_noise_t_call_key(text_value):
                                i18n_dict[text_value] = text_value
                        index = next_index
                        continue

        if script_content.startswith("translate", index):
            previous_char = script_content[index - 1] if index > 0 else ""
            after_index = index + len("translate")
            if (
                not is_identifier_char(previous_char)
                and previous_char != "."
                and (after_index >= len(script_content) or not is_identifier_char(script_content[after_index]))
            ):
                whitespace_index = after_index
                while whitespace_index < len(script_content) and script_content[whitespace_index].isspace():
                    whitespace_index += 1
                if whitespace_index < len(script_content) and script_content[whitespace_index] == "(":
                    next_index, arguments = parse_js_call_arguments(script_content, whitespace_index)
                    if arguments:
                        text_value = parse_static_js_value(arguments[0]) if len(arguments) > 0 else None
                        key_value = parse_static_js_value(arguments[1]) if len(arguments) > 1 else None
                        final_key = key_value or text_value
                        if final_key:
                            i18n_dict[final_key] = text_value if text_value is not None else final_key
                    index = next_index
                    continue

        if script_content.startswith("applyLocale", index):
            previous_char = script_content[index - 1] if index > 0 else ""
            after_index = index + len("applyLocale")
            if (
                not is_identifier_char(previous_char)
                and (after_index >= len(script_content) or not is_identifier_char(script_content[after_index]))
            ):
                whitespace_index = after_index
                while whitespace_index < len(script_content) and script_content[whitespace_index].isspace():
                    whitespace_index += 1
                if whitespace_index < len(script_content) and script_content[whitespace_index] == "(":
                    next_index, arguments = parse_js_call_arguments(script_content, whitespace_index)
                    extracted = False
                    if arguments:
                        html_value = parse_static_js_value(arguments[0]) if len(arguments) > 0 else None
                        if html_value and "data-i18n" in html_value:
                            merge_i18n_entries(i18n_dict, extract_i18n_keys_from_html(html_value))
                            extracted = True
                    if extracted:
                        index = next_index
                        continue

        if script_content.startswith("attr", index):
            previous_char = script_content[index - 1] if index > 0 else ""
            after_index = index + len("attr")
            if not is_identifier_char(previous_char) and (
                after_index >= len(script_content) or not is_identifier_char(script_content[after_index])
            ):
                whitespace_index = after_index
                while whitespace_index < len(script_content) and script_content[whitespace_index].isspace():
                    whitespace_index += 1
                if whitespace_index < len(script_content) and script_content[whitespace_index] == "(":
                    next_index, arguments = parse_js_call_arguments(script_content, whitespace_index)
                    extracted = False
                    if arguments and len(arguments) > 1:
                        target_attribute = parse_static_js_value(arguments[0])
                        i18n_value = parse_static_js_value(arguments[1])
                        if target_attribute == "data-i18n" and i18n_value:
                            merge_i18n_entries(i18n_dict, extract_i18n_keys_from_data_i18n_value(i18n_value))
                            extracted = True
                    if extracted:
                        index = next_index
                        continue

        if script_content.startswith("setAttribute", index):
            previous_char = script_content[index - 1] if index > 0 else ""
            after_index = index + len("setAttribute")
            if not is_identifier_char(previous_char) and (
                after_index >= len(script_content) or not is_identifier_char(script_content[after_index])
            ):
                whitespace_index = after_index
                while whitespace_index < len(script_content) and script_content[whitespace_index].isspace():
                    whitespace_index += 1
                if whitespace_index < len(script_content) and script_content[whitespace_index] == "(":
                    next_index, arguments = parse_js_call_arguments(script_content, whitespace_index)
                    extracted = False
                    if arguments and len(arguments) > 1:
                        target_attribute = parse_static_js_value(arguments[0])
                        i18n_value = parse_static_js_value(arguments[1])
                        if target_attribute == "data-i18n" and i18n_value:
                            merge_i18n_entries(i18n_dict, extract_i18n_keys_from_data_i18n_value(i18n_value))
                            extracted = True
                    if extracted:
                        index = next_index
                        continue

        if script_content.startswith("dataset.i18n", index):
            previous_char = script_content[index - 1] if index > 0 else ""
            after_index = index + len("dataset.i18n")
            if not is_identifier_char(previous_char):
                whitespace_index = after_index
                while whitespace_index < len(script_content) and script_content[whitespace_index].isspace():
                    whitespace_index += 1
                if whitespace_index < len(script_content) and script_content[whitespace_index] == "=":
                    expression_start = whitespace_index + 1
                    while expression_start < len(script_content) and script_content[expression_start].isspace():
                        expression_start += 1
                    next_index, assignment_expression = parse_js_assignment_expression(script_content, expression_start)
                    i18n_value = parse_static_js_value(assignment_expression)
                    if i18n_value:
                        merge_i18n_entries(i18n_dict, extract_i18n_keys_from_data_i18n_value(i18n_value))
                        index = next_index
                        continue

        index += 1

    return i18n_dict


def collect_source_files(directory):
    source_files = []

    for root, dirs, files in os.walk(directory):
        dirs[:] = sorted(
            directory_name
            for directory_name in dirs
            if not should_skip_path(os.path.join(root, directory_name), directory)
        )
        for file_name in sorted(files):
            if not file_name.lower().endswith(SOURCE_EXTENSIONS):
                continue
            file_path = os.path.join(root, file_name)
            if should_skip_path(file_path, directory):
                continue
            source_files.append(file_path)

    source_files.sort(key=lambda path: normalize_relative_path(path, directory))
    return source_files


def process_source_files(directory):
    i18n_data = OrderedDict()
    key_source_positions = {}
    source_files = collect_source_files(directory)

    for source_file in source_files:
        with open(source_file, "r", encoding="utf-8") as file:
            source_content = file.read()

        if source_file.lower().endswith(".html"):
            extracted = extract_i18n_keys_from_html(source_content)
        else:
            extracted = extract_i18n_keys_from_scripts(source_content)

        normalized_source_path = normalize_relative_path(source_file, directory)
        for key_index, key in enumerate(extracted.keys()):
            if key and key not in key_source_positions:
                key_source_positions[key] = (normalized_source_path, key_index)

        merge_i18n_entries(i18n_data, extracted)

    return i18n_data, key_source_positions


def update_json(json_file, i18n_dict, key_source_positions=None, flags=None, run_totals=None):
    # Backward compatibility: allow update_json(json_file, i18n_dict, flags)
    if flags is None and isinstance(key_source_positions, dict):
        flag_keys = {"sort_keys", "auto_remove", "auto_add", "auto_translate"}
        if set(key_source_positions.keys()).issubset(flag_keys):
            flags = key_source_positions
            key_source_positions = None

    if flags is None:
        flags = {
            "sort_keys": True,
            "auto_remove": False,
            "auto_add": True,
            "auto_translate": False,
        }
    if key_source_positions is None:
        key_source_positions = {}

    data, duplicate_keys = load_json_with_first_key_wins(json_file)

    target_name = os.path.splitext(os.path.basename(json_file))[0]
    display_path = format_display_path(json_file)
    print_status("FIL", target_name, color="cyan")

    counters = {
        "nf": 0,
        "add": 0,
        "skip": 0,
        "dup": 0,
        "extra": 0,
        "remove": 0,
        "err": 0,
    }

    if duplicate_keys:
        counters["dup"] = len(duplicate_keys)
        for key in duplicate_keys:
            print_status("DUP", f"{key}  (keep first occurrence)", color="yellow")

    try:
        language = json_file.replace("\\", "/").split("/")[-1].split(".")[0]
        for key in i18n_dict.keys():
            if key not in data:
                counters["nf"] += 1
                print_status("NF", key, color="yellow")
                if i18n_dict[key] == "":
                    counters["skip"] += 1
                    print_status("SKP", f"Empty key value: {key}", color="gray")
                if flags["auto_add"] and i18n_dict[key] != "":
                    if flags["auto_translate"]:
                        try:
                            data[key] = GoogleTranslator(source="en", target=language).translate(i18n_dict[key])
                            counters["add"] += 1
                            print_status("ADD", f"{key}  (translated)", color="green")
                        except Exception as x:
                            if "No support for the provided language" in str(x):
                                language = language.split("-")[0] + "-" + language.split("-")[1].upper()
                                try:
                                    data[key] = GoogleTranslator(source="en", target=language).translate(i18n_dict[key])
                                    counters["add"] += 1
                                    print_status("ADD", f"{key}  (translated)", color="green")
                                except Exception as y:
                                    if "No support for the provided language" in str(y):
                                        language = language.split("-")[0]
                                        data[key] = GoogleTranslator(source="en", target=language).translate(i18n_dict[key])
                                        counters["add"] += 1
                                        print_status("ADD", f"{key}  (translated)", color="green")
                    else:
                        data[key] = i18n_dict[key]
                        counters["add"] += 1
                        print_status("ADD", key, color="green")

    except Exception as e:
        counters["err"] += 1
        print_status("ERR", f"Error processing '{json_file}': {e}", color="red", stream=sys.stderr)

    for key in list(data.keys()):
        if key not in i18n_dict:
            counters["extra"] += 1
            print_status("EXT", key, color="magenta")
            if flags["auto_remove"]:
                del data[key]
                counters["remove"] += 1
                print_status("DEL", key, color="red")

    if flags["sort_keys"]:
        sorted_keys = sorted(
            data.keys(),
            key=lambda key: (
                0 if key in i18n_dict else 1,
                key_source_positions.get(key, ("", sys.maxsize))[0],
                key_source_positions.get(key, ("", sys.maxsize))[1],
                key.casefold(),
                key,
            ),
        )
        data = OrderedDict((key, data[key]) for key in sorted_keys)

    with open(json_file, "w", encoding="utf-8", newline="\n") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)
        file.write("\n")

    print_status(
        "SUM",
        f"{target_name} | NF:{counters['nf']} ADD:{counters['add']} DUP:{counters['dup']} EXT:{counters['extra']} DEL:{counters['remove']} SKP:{counters['skip']} | {display_path}",
        color="blue",
    )

    if run_totals is not None:
        for key in ("nf", "add", "skip", "dup", "extra", "remove", "err"):
            run_totals[key] = run_totals.get(key, 0) + counters[key]

    return data


if __name__ == "__main__":
    argparser = argparse.ArgumentParser(description="Update or Generate i18n JSON files")
    argparser.add_argument("json", help="JSON file path", type=str)
    argparser.add_argument("-d", "--directory", help="Directory path", type=str, default="./public")
    argparser.add_argument(
        "--auto-add",
        help="Auto add missing keys",
        action="store_true",
        default=True,
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
        default=False,
    )
    argparser.add_argument(
        "--sort-keys",
        help="Sort keys by project tree order (source path + first appearance in file)",
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
        print_status("ERR", f"Directory '{directory_path}' not found.", color="red", stream=sys.stderr)
        exit(1)

    locales_path = os.path.join(directory_path, "locales")
    all_i18n_data, key_source_positions = process_source_files(directory_path)
    flags = {
        "auto_add": args.auto_add,
        "auto_translate": args.auto_translate,
        "auto_remove": args.auto_remove,
        "sort_keys": args.sort_keys,
    }
    run_totals = create_run_totals()

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
                print_status("ERR", f"JSON file '{json_file_path}' not found.", color="red", stream=sys.stderr)
                exit(1)
        updated_json = update_json(json_file_path, all_i18n_data, key_source_positions, flags, run_totals)
        run_totals["files"] += 1
    else:
        print_status("RUN", "Updating all JSON files...", color="cyan")
        for json_file in os.listdir(locales_path):
            if (
                json_file.endswith(".json")
                and not json_file.endswith("lang.json")
                and not json_file.endswith("en.json")
            ):
                json_file_path = os.path.join(locales_path, json_file)
                updated_json = update_json(json_file_path, all_i18n_data, key_source_positions, flags, run_totals)
                run_totals["files"] += 1
    total_parts = []
    if run_totals["files"] > 1:
        total_parts.append(f"FILES:{run_totals['files']}")
    total_parts.extend(
        [
            f"NF:{run_totals['nf']}",
            f"ADD:{run_totals['add']}",
            f"DUP:{run_totals['dup']}",
            f"EXT:{run_totals['extra']}",
            f"DEL:{run_totals['remove']}",
            f"SKP:{run_totals['skip']}",
            f"ERR:{run_totals['err']}",
        ]
    )
    print_status("TOT", " ".join(total_parts), color="cyan")
    print_status("OK", "Done!", color="green")
