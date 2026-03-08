import os
import hashlib
import sys

# macOSのAPFSやLinuxのext4/overlayを考慮し、全角半角混在でも安全なように文字数で制限
# 日本語1文字=最大約4バイト考慮、Linuxの255 bytes制限に余裕を持たせるため
# 名前自体は40文字＋ハッシュ8文字程度に抑える。
MAX_NAME_LENGTH = 40 

def truncate_and_hash(original_name, is_dir=False):
    """
    Truncate naming and append a hash of original name to prevent collisions.
    Resulting pattern: [Truncated_Name]_[Short_Hash].[ext]
    """
    # Exclude extension for files
    if not is_dir and "." in original_name:
        name_part, ext = original_name.rsplit(".", 1)
        ext = "." + ext
    else:
        name_part = original_name
        ext = ""

    # Generate a short hash (8 chars) from the ORIGINAL full name (pre-extension)
    hash_str = hashlib.md5(original_name.encode('utf-8')).hexdigest()[:8]

    # Clean the name (optional but recommended for syncing)
    truncated_name = name_part[:MAX_NAME_LENGTH].strip()
    
    # Reassemble: "Short Name_a1b2c3d4.md"
    new_name = f"{truncated_name}_{hash_str}{ext}"
    return new_name

def prepend_original_name_to_file(filepath, original_name):
    """
    Prepend the original full name to the beginning of the markdown file.
    """
    if not filepath.endswith(".md"):
        return # Only alter markdown files

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading file {filepath}: {e}")
        return

    # Check if we already appended it (rerun safety)
    if "<!-- Original Name:" in content[:200]: 
        return

    # Frontmatter or simple text
    # original_name[:-3] removes '.md'
    display_title = original_name[:-3] if original_name.endswith('.md') else original_name
    
    preamble = f"<!-- Original Name: {original_name} -->\n"
    preamble += f"# {display_title}\n\n"

    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(preamble + content)
    except Exception as e:
        print(f"Error writing to file {filepath}: {e}")


def process_directory_tree(root_dir):
    """
    Process directories and files bottom-up (using os.walk with topdown=False)
    This ensures that renaming a parent directory doesn't break the paths of its children we still need to process.
    """
    count_files = 0
    count_dirs = 0

    for dirpath, dirnames, filenames in os.walk(root_dir, topdown=False):
        
        # 1. Process files in current directory
        for filename in filenames:
            # Check length of the string (characters, not bytes)
            # Japanese character is length=1 in python, but takes 3 bytes in UTF-8
            # 40 chars * 3 = 120 bytes, safely under 255 bytes.
            if len(filename) > MAX_NAME_LENGTH:
                count_files += 1
                old_filepath = os.path.join(dirpath, filename)
                new_filename = truncate_and_hash(filename, is_dir=False)
                new_filepath = os.path.join(dirpath, new_filename)
                
                print(f"[FILE] Renaming:\n  Old: {filename}\n  New: {new_filename}")
                
                # Prepend original name internally
                prepend_original_name_to_file(old_filepath, filename)
                
                # Perform rename
                os.rename(old_filepath, new_filepath)

        # 2. Process directory name itself
        dir_name = os.path.basename(dirpath)
        
        # Skip root_dir itself
        if dirpath != root_dir and len(dir_name) > MAX_NAME_LENGTH:
            count_dirs += 1
            parent_dir = os.path.dirname(dirpath)
            new_dirname = truncate_and_hash(dir_name, is_dir=True)
            new_dirpath = os.path.join(parent_dir, new_dirname)
            
            print(f"[DIR] Renaming:\n  Old: {dir_name}\n  New: {new_dirname}")
            
            # Perform rename
            os.rename(dirpath, new_dirpath)

    return count_files, count_dirs

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/shorten_notion_names.py /path/to/ObsidianVault/notion")
        sys.exit(1)
        
    target_dir = sys.argv[1]
    target_dir = os.path.abspath(target_dir) # Convert to absolute path
    
    if not os.path.exists(target_dir):
        print(f"Error: Directory '{target_dir}' does not exist.")
        sys.exit(1)
        
    print(f"Scanning and shortening names in: {target_dir}")
    print("==================================================")
    f_count, d_count = process_directory_tree(target_dir)
    print("==================================================")
    print(f"Done! Shortened {f_count} files and {d_count} directories.")
