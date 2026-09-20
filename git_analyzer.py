import os
import io
import zipfile
import logging
import requests

logger = logging.getLogger(__name__)

MAX_ZIP_SIZE = 20 * 1024 * 1024 

def fetch_github_repo(repo_url_or_path):
    path = repo_url_or_path.replace("https://", "").replace("http://", "").replace("github.com/", "").strip()
    parts = [p for p in path.split("/") if p]
    if len(parts) < 2:
        return None, "❌ Неверный формат ссылки. Используй: `/gitv owner/repo` или полную ссылку на GitHub."
    
    owner, repo = parts[0], parts[1]
    zip_url = f"https://api.github.com/repos/{owner}/{repo}/zipball"
    headers = {"User-Agent": "Sosaltix-Bot"}
    
    urls_to_try = [
        zip_url,
        f"https://github.com/{owner}/{repo}/archive/refs/heads/main.zip",
        f"https://github.com/{owner}/{repo}/archive/refs/heads/master.zip"
    ]

    for url in urls_to_try:
        try:
            response = requests.get(url, headers=headers, stream=True, timeout=15)
            if response.status_code == 200:
                content_length = response.headers.get("Content-Length")
                if content_length and int(content_length) > MAX_ZIP_SIZE:
                    return None, "❌ Репозиторий слишком большой (превышает 15 МБ)."
                
                buffer = io.BytesIO()
                downloaded = 0
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        downloaded += len(chunk)
                        if downloaded > MAX_ZIP_SIZE:
                            return None, "❌ Репозиторий слишком большой (превышает 15 МБ)."
                        buffer.write(chunk)
                
                buffer.seek(0)
                zip_file = zipfile.ZipFile(buffer)
                return zip_file, None
        except Exception as e:
            logger.warning(f"Ошибка скачивания {url}: {e}")
            continue

    return None, f"❌ Не удалось скачать репозиторий {owner}/{repo}. Проверь ссылку."

def process_repo_zip(zip_file):
    allowed_exts = {'.rs', '.c', '.cpp', '.h', '.hpp', '.py', '.js', '.ts', '.go', '.sh', '.asm', '.s', '.json', '.toml', '.md', '.txt', '.java', '.kt', '.cs'}
    ignored_dirs = {'node_modules', '.git', '.github', 'target', 'build', 'dist', 'venv', 'env', '__pycache__', 'cmake-build-debug', 'obj', 'bin'}
    
    tree_lines = []
    file_contents = []
    total_chars = 0
    MAX_CHARS = 30000

    namelist = zip_file.namelist()
    if not namelist:
        return "Репозиторий пуст.", ""

    root_dir = namelist[0].split('/')[0] + '/'
    
    for name in sorted(namelist):
        clean_name = name[len(root_dir):] if name.startswith(root_dir) else name
        if not clean_name:
            continue
        
        parts = clean_name.split('/')
        if any(ignored in parts for ignored in ignored_dirs):
            continue
        
        if name.endswith('/'):
            indent = '  ' * (len(parts) - 2)
            tree_lines.append(f"{indent}📁 {parts[-2]}/")
            continue
        
        indent = '  ' * (len(parts) - 1)
        file_name = parts[-1]
        tree_lines.append(f"{indent}📄 {file_name}")
        
        _, ext = os.path.splitext(file_name.lower())
        if ext in allowed_exts and total_chars < MAX_CHARS:
            try:
                content = zip_file.read(name).decode('utf-8', errors='ignore')
                if content.strip():
                    chunk = content[:6000]
                    if len(content) > 6000:
                        chunk += "\n... [файл обрезан] ..."
                    file_contents.append(f"--- ФАЙЛ: {clean_name} ---\n```\n{chunk}\n```")
                    total_chars += len(chunk)
            except Exception as e:
                logger.debug(f"Ошибка чтения файла {name}: {e}")
                
    tree_str = "\n".join(tree_lines[:150])
    if len(tree_lines) > 150:
        tree_str += "\n... [дерево файлов обрезано] ..."
        
    code_str = "\n\n".join(file_contents)
    return tree_str, code_str
