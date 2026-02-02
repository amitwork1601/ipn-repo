import os
import sys
import yaml
import subprocess
import re
import shutil
import json
from pathlib import Path

try:
    from anthropic import Anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    print("Warning: anthropic library not installed. AI enhancement disabled.")

# ---------------------------------------------------------------------------
# AI Enhancer (unchanged)
# ---------------------------------------------------------------------------
class AIDocumentationEnhancer:
    """Enhances documentation using AI (Claude API)"""

    def __init__(self, config):
        self.enabled = config.get('enabled', False) and ANTHROPIC_AVAILABLE
        self.provider = config.get('provider', 'claude')
        self.model = config.get('model', 'claude-sonnet-4-20250514')
        if self.enabled:
            api_key = config.get('api_key')
            if not api_key:
                print("Warning: AI enhancement enabled but no API key provided")
                self.enabled = False
            else:
                try:
                    self.client = Anthropic(api_key=api_key)
                    print(f"[AI] Enhancement enabled using {self.provider} ({self.model})")
                except Exception as e:
                    print(f"Warning: Failed to initialize Claude client: {e}")
                    self.enabled = False

    def enhance_file_summary(self, file_path, code_snippet, basic_summary, classes, functions):
        """Generate an intelligent summary for a file"""
        if not self.enabled:
            return basic_summary
        # Limit code snippet to avoid token limits
        code_preview = code_snippet[:2000] if code_snippet else ""
        prompt = f"""Analyze this code file and provide a concise 2-3 sentence summary of its purpose and main functionality.

File: {file_path}
Classes: {', '.join(classes) if classes else 'None'}
Functions: {', '.join(functions[:10]) if functions else 'None'}

Code preview:
{code_preview}

Current basic summary: {basic_summary}

Provide a clear, technical summary. Focus on WHAT the code does and WHY it exists. Be specific about the domain/business logic."""
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}]
            )
            enhanced = response.content[0].text.strip()
            return enhanced if enhanced else basic_summary
        except Exception as e:
            print(f"AI enhancement failed for {file_path}: {e}")
            return basic_summary

    def enhance_function_doc(self, function_name, params, code_snippet, basic_doc):
        """Generate an intelligent description for a function"""
        if not self.enabled or not code_snippet:
            return basic_doc
        code_preview = code_snippet[:500]
        prompt = f"""Explain what this function does in 1 sentence. Be concise and technical.

Function: {function_name}({params})
Code:
{code_preview}

Provide only the description, no preamble."""
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=100,
                messages=[{"role": "user", "content": prompt}]
            )
            enhanced = response.content[0].text.strip()
            return enhanced if enhanced else basic_doc
        except Exception:
            return basic_doc

# ---------------------------------------------------------------------------
# Config Loader
# ---------------------------------------------------------------------------
class ConfigLoader:
    @staticmethod
    def load(config_path):
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)

# ---------------------------------------------------------------------------
# Repository handling (multiple repos)
# ---------------------------------------------------------------------------
class RepoManager:
    def __init__(self, name, repo_url, local_path, token=None):
        self.name = name
        self.repo_url = repo_url
        self.local_path = local_path
        self.token = token

    def setup(self):
        # Skip git operations for local file:// URLs
        if self.repo_url and self.repo_url.startswith("file://"):
            print(f"Using local repository {self.name} at {self.local_path}...")
            if not os.path.exists(self.local_path):
                print(f"Error: Local path {self.local_path} does not exist")
                sys.exit(1)
            return
        
        git_cmd = shutil.which("git")
        if not git_cmd:
            print("Error: 'git' executable not found in PATH.")
            print(f"Current PATH: {os.environ.get('PATH')}")
            sys.exit(1)

        if os.path.exists(self.local_path):
            print(f"Updating repository {self.name} in {self.local_path}...")
            try:
                subprocess.run([git_cmd, "-C", self.local_path, "pull"], check=True)
            except subprocess.CalledProcessError as e:
                print(f"Error pulling repository {self.name}: {e}")
        else:
            print(f"Cloning repository {self.name} to {self.local_path}...")
            url = self.repo_url
            if self.token:
                if "https://" in url:
                    url = url.replace("https://", f"https://{self.token}@")
            try:
                subprocess.run([git_cmd, "clone", url, self.local_path], check=True)
            except subprocess.CalledProcessError as e:
                print(f"Error cloning repository {self.name}: {e}")
                sys.exit(1)

# ---------------------------------------------------------------------------
# Parser utilities (unchanged)
# ---------------------------------------------------------------------------
class ParserUtils:
    @staticmethod
    def extract_docstring(content):
        """Extracts top-level docstrings or comments."""
        # PHP style multiline
        match = re.search(r'/\*\*([\s\S]*?)\*/', content)
        if match:
            return ParserUtils.clean_comment(match.group(1))
        # Python style
        match = re.search(r'"""([\s\S]*?)"""', content)
        if match:
            return ParserUtils.clean_comment(match.group(1))
        return ""

    @staticmethod
    def clean_comment(comment):
        if not comment:
            return ""
        comment = re.sub(r'^/\*\*|^\s*\*/', '', comment.strip())
        lines = [re.sub(r'^\s*\*\s?', '', line).strip() for line in comment.split('\n')]
        while lines and not lines[0]:
            lines.pop(0)
        while lines and not lines[-1]:
            lines.pop()
        return '\n'.join(lines)

    @staticmethod
    def smart_summary(name):
        name = name.replace('_', ' ')
        name = re.sub(r'(?<!^)(?=[A-Z])', ' ', name)
        return name.strip()

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Language parsers
# ---------------------------------------------------------------------------
class GenericParser:
    def parse(self, content):
        return {
            'summary': ParserUtils.extract_docstring(content),
            'classes': [],
            'methods': {},
            'routes': []
        }

class PHPParser:
    def parse(self, content):
        info = {
            'summary': ParserUtils.extract_docstring(content),
            'classes': [],
            'methods': {},
            'routes': [],
            'dependencies': []
        }
        # Extract classes
        classes = re.findall(r'class\s+(\w+)', content)
        info['classes'] = classes
        
        # Extract functions with docblocks
        pattern = r'(/\*\*[\s\S]*?\*/\s*)?(?:public|private|protected|static)?\s*function\s+(\w+)\s*\((.*?)\)'
        matches = re.finditer(pattern, content)
        for match in matches:
            docblock = match.group(1)
            func_name = match.group(2)
            params = match.group(3)
            doc = ParserUtils.clean_comment(docblock) if docblock else ""
            info['methods'][func_name] = {
                'params': params,
                'doc': doc
            }
            
        # Extract routes (Symfony/Laravel style annotations)
        routes = re.findall(r'@Route\("([^"]+)"', content)
        info['routes'] = routes
        
        # Extract dependencies
        # 1. Imports (use ...)
        uses = re.findall(r'use\s+([\w\\]+);', content)
        # Keep only the class name from full namespace
        info['dependencies'].extend([u.split('\\')[-1] for u in uses])
        
        # 2. Instantiations (new ClassName)
        instantiations = re.findall(r'new\s+(\w+)', content)
        info['dependencies'].extend(instantiations)
        
        # 3. Type hints in methods
        type_hints = re.findall(r'function\s+\w+\s*\((.*?)\)', content)
        for params in type_hints:
            # Match "Type $var"
            hints = re.findall(r'(\w+)\s+\$\w+', params)
            # Filter out basic types
            basics = ['string', 'int', 'bool', 'float', 'array', 'object', 'callable', 'iterable', 'void', 'mixed', 'null', 'false', 'true', 'never']
            hints = [h for h in hints if h.lower() not in basics]
            info['dependencies'].extend(hints)
            
        # Deduplicate
        info['dependencies'] = list(set(info['dependencies']))
        
        return info

class JSParser:
    def parse(self, content):
        info = {
            'summary': ParserUtils.extract_docstring(content),
            'classes': [],
            'methods': {},
            'routes': [],
            'dependencies': []
        }
        
        # Extract dependencies
        # 1. Imports (import ... from '...')
        imports = re.findall(r'import\s+(?:[\w\s{},*]+)\s+from\s+[\'"](.+?)[\'"]', content)
        for imp in imports:
            name = imp.split('/')[-1].replace('.js', '').replace('.ts', '').replace('.vue', '')
            info['dependencies'].append(name)
            
        # 2. Require
        requires = re.findall(r'require\s*\(\s*[\'"](.+?)[\'"]\s*\)', content)
        for req in requires:
            name = req.split('/')[-1].replace('.js', '').replace('.ts', '')
            info['dependencies'].append(name)
            
        # 3. Instantiations
        instantiations = re.findall(r'new\s+(\w+)', content)
        info['dependencies'].extend(instantiations)
        
        # Deduplicate
        info['dependencies'] = list(set(info['dependencies']))
        # Classes
        info['classes'] = re.findall(r'class\s+(\w+)', content)
        # Functions
        matches = re.finditer(r'(?:async\s+)?function\s+(\w+)\s*\((.*?)\)', content)
        for match in matches:
            info['methods'][match.group(1)] = {'params': match.group(2), 'doc': ''}
        # Arrow functions
        matches = re.finditer(r'const\s+(\w+)\s*=\s*(?:async\s+)?\(?(.*?)\)?\s*=>', content)
        for match in matches:
            info['methods'][match.group(1)] = {'params': match.group(2), 'doc': ''}
        return info

class VueParser(JSParser):
    def parse(self, content):
        # Extract script content
        script_match = re.search(r'<script[^>]*>([\s\S]*?)</script>', content)
        if script_match:
            return super().parse(script_match.group(1))
        return super().parse(content)

class TypeScriptParser(JSParser):
    """Parser for TypeScript and TSX files"""
    def parse(self, content):
        info = super().parse(content)
        # Additional TS-specific dependency extraction could go here
        # Extract interfaces
        interfaces = re.findall(r'interface\s+(\w+)', content)
        if interfaces:
            info['interfaces'] = interfaces
        # Extract type aliases
        types = re.findall(r'type\s+(\w+)\s*=', content)
        if types:
            info['types'] = types
        # Extract enums
        enums = re.findall(r'enum\s+(\w+)', content)
        if enums:
            info['enums'] = enums
        # Extract decorators (for Angular, NestJS, etc.)
        decorators = re.findall(r'@(\w+)\(', content)
        if decorators:
            info['decorators'] = list(set(decorators))
        return info

class MDXParser:
    def parse(self, content):
        return {
            'summary': content[:200].replace('\n', ' '),
            'classes': [],
            'methods': {},
            'routes': []
        }

class GherkinParser:
    def parse(self, content):
        scenarios = re.findall(r'Scenario:\s*(.*)', content)
        return {
            'summary': "Gherkin Feature File",
            'classes': [],
            'methods': {s: {'params': '', 'doc': 'Scenario'} for s in scenarios},
            'routes': []
        }

# ---------------------------------------------------------------------------
# Markdown Generator – extended to track repo and support merging
# ---------------------------------------------------------------------------
class MarkdownGenerator:
    def __init__(self, output_dir, ai_enhancer=None):
        self.output_dir = Path(output_dir)
        self.output_dir = Path(output_dir)
        # Tree is now a dict of dicts: repo_type -> category -> files
        self.trees = {
            'backend': {},
            'frontend': {},
            'other': {}
        }
        self.ai_enhancer = ai_enhancer
        self.file_repo_map = {}  # filename -> repo name
        self.repo_type_map = {}  # repo name -> type (backend/frontend)
        self.file_tags_map = {}  # filename -> list of tags
        self.dependencies_map = {} # filename -> list of dependencies
        self.class_to_path_map = {} # ClassName -> doc path
        self.functional_scopes = {} # scope configuration
        self.categories = {
            'Controllers': [],
            'Entities': [],
            'Services': [],
            'Repositories': [],
            'Commands': [],
            'Events': [],
            'Plugins': [],
            'Other': []
        }

    def register_repo_type(self, repo_name, repo_type):
        self.repo_type_map[repo_name] = repo_type

    @staticmethod
    def escape_markdown(text):
        if not text:
            return text
        return (
            text.replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
        )

    def get_category(self, file_path):
        path_str = str(file_path).lower()
        if 'controller' in path_str:
            return 'Controllers'
        if 'entity' in path_str:
            return 'Entities'
        if 'repository' in path_str:
            return 'Repositories'
        if 'service' in path_str:
            return 'Services'
        if 'command' in path_str:
            return 'Commands'
        if 'event' in path_str or 'listener' in path_str:
            return 'Events'
        if 'plugin' in path_str:
            return 'Plugins'
        return 'Other'

    def add_to_tree(self, path_parts, link, category, repo_type='other'):
        # Determine which tree to use
        target_tree = self.trees.get(repo_type, self.trees['other'])
        
        if category not in target_tree:
            target_tree[category] = {}
        current = target_tree[category]
        
        start_idx = 0
        if path_parts[0] in ['src', 'app']:
            start_idx = 1
        for part in path_parts[start_idx:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]
            if isinstance(current, str):
                current = {}
        current[path_parts[-1]] = link

    def generate_summary_lines(self, tree, level=0):
        lines = []
        indent = "  " * level
        for key in sorted(tree.keys()):
            value = tree[key]
            if isinstance(value, dict):
                lines.append(f"{indent}- **{key}**")
                lines.extend(self.generate_summary_lines(value, level + 1))
            else:
                lines.append(f"{indent}- {value}")
        return lines

    def compute_tags(self, file_path):
        tags = []
        path_str = str(file_path).lower()
        name_str = Path(file_path).name.lower()
        
        for scope, rules in self.functional_scopes.items():
            # Check paths
            for path_k in rules.get('paths', []):
                if path_k.lower() in path_str:
                    tags.append(scope)
                    break
            # Check keywords in filename
            if scope not in tags:
                for kw in rules.get('keywords', []):
                    if kw.lower() in name_str:
                        tags.append(scope)
                        break
        return list(set(tags))

    def generate(self, file_path, info, root_dir, repo_name, code_content=''):
        # Document ALL files - don't skip any
        # Previously skipped files without classes/functions, but user wants ALL files documented
        rel_path = Path(file_path).relative_to(root_dir)
        safe_name = str(rel_path).replace(os.sep, '_').replace('.', '_') + '.md'
        doc_path = self.output_dir / safe_name
        
        category = self.get_category(file_path)
        tags = self.compute_tags(file_path)
        
        # Record data for index
        self.file_repo_map[safe_name] = repo_name
        self.file_tags_map[safe_name] = tags
        
        # Track dependencies
        self.dependencies_map[safe_name] = info.get('dependencies', [])
        
        # Add to navigation tree
        link = f"[{rel_path.name}]({safe_name})"
        repo_type = self.repo_type_map.get(repo_name, 'other')
        self.add_to_tree(rel_path.parts, link, category, repo_type)

        # Incremental Generation: Skip if file already exists to save API costs
        if doc_path.exists():
            print(f"[Skip] Documentation already exists for {rel_path}")
            return True
            
        doc_path.parent.mkdir(parents=True, exist_ok=True)

        # AI enhancement
        if self.ai_enhancer and self.ai_enhancer.enabled:
            enhanced_summary = self.ai_enhancer.enhance_file_summary(
                str(rel_path), code_content, info.get('summary', ''),
                info.get('classes', []), info.get('functions', []))
            if enhanced_summary:
                info['summary'] = enhanced_summary
        
        # Write markdown
        with open(doc_path, 'w', encoding='utf-8') as f:
            f.write(f"# {rel_path.name}\n\n")
            
            # Metadata Badge
            f.write(f"**Path**: `{rel_path}`  \n")
            if tags:
                tag_str = ", ".join([f"`{t}`" for t in tags])
                f.write(f"**Functional Scope**: {tag_str}\n\n")
            else:
                f.write("\n")

            if info.get('summary'):
                summary_text = self.escape_markdown(info['summary'])
                f.write(f"## Purpose\n{summary_text}\n\n")
            
            # Dependencies Link Section
            deps = info.get('dependencies', [])
            if deps:
                f.write("## Dependencies\n")
                f.write("This component uses:\n")
                for dep in deps:
                    # Resolve link
                    if dep in self.class_to_path_map:
                        link_path = self.class_to_path_map[dep]
                        f.write(f"- [`{dep}`]({link_path})\n")
                    elif dep.lower() in self.class_to_path_map:
                         link_path = self.class_to_path_map[dep.lower()]
                         f.write(f"- [`{dep}`]({link_path})\n")
                    else:
                        f.write(f"- `{dep}`\n")
                f.write("\n")
            
            if info.get('classes'):
                f.write("## Classes\n")
                for cls in info['classes']:
                    f.write(f"- `{cls}`\n")
                f.write("\n")
            # TypeScript-specific sections
            if info.get('interfaces'):
                f.write("## Interfaces\n")
                for iface in info['interfaces']:
                    f.write(f"- `{iface}`\n")
                f.write("\n")
            if info.get('types'):
                f.write("## Type Aliases\n")
                for typ in info['types']:
                    f.write(f"- `{typ}`\n")
                f.write("\n")
            if info.get('enums'):
                f.write("## Enums\n")
                for enum in info['enums']:
                    f.write(f"- `{enum}`\n")
                f.write("\n")
            if info.get('decorators'):
                f.write("## Decorators\n")
                for dec in info['decorators']:
                    f.write(f"- `@{dec}`\n")
                f.write("\n")
            if info.get('methods'):
                f.write("## Function Details\n\n")
                for func_name, details in info['methods'].items():
                    f.write(f"### `{func_name}`\n\n")
                    if details.get('params'):
                        f.write(f"- **Parameters**: `{details['params']}`\n")
                    if details.get('doc'):
                        desc = self.escape_markdown(details['doc'])
                        f.write(f"- **Description**: {desc}\n")
                    f.write("\n")
            if info.get('routes'):
                f.write("## API Routes\n")
                for route in info['routes']:
                    f.write(f"- `{route}`\n")
                f.write("\n")
        return True

    def write_index(self):
        lines = ["# Documentation Index\n"]
        priority_order = ['Controllers', 'Services', 'Entities', 'Repositories', 'Commands', 'Events', 'Plugins', 'Other']
        
        # Helper to generate lines for a specific tree
        def write_section(tree, section_title):
            section_lines = []
            has_content = False
            
            # Check if tree has any content
            for cat in priority_order:
                if cat in tree and tree[cat]:
                    has_content = True
                    break
            
            if has_content:
                section_lines.append(f"## {section_title}\n")
                for category in priority_order:
                    if category in tree and tree[category]:
                        section_lines.append(f"### {category}\n")
                        section_lines.extend(self.generate_summary_lines(tree[category]))
                        section_lines.append("\n")
            return section_lines

        # Write Backend Section
        lines.extend(write_section(self.trees.get('backend', {}), "Backend"))
        
        # Write Frontend Section
        lines.extend(write_section(self.trees.get('frontend', {}), "Frontend"))
        
        # Write Other Section
        lines.extend(write_section(self.trees.get('other', {}), "Other / Shared"))

        with open(self.output_dir / "SUMMARY.md", 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))

    def write_web_index(self):
        """Generate JSON index consumed by the interactive viewer."""
        files_data = []
        for md_file in self.output_dir.glob("*.md"):
            if md_file.name == "SUMMARY.md":
                continue
            try:
                with open(md_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                title = lines[0].replace('#', '').strip() if lines else md_file.stem
                summary = ""
                in_summary = False
                for line in lines:
                    if line.startswith('## Summary'):
                        in_summary = True
                        continue
                    if in_summary and line.startswith('##'):
                        break
                    if in_summary:
                        summary += line
                summary = summary.strip()[:200]
                category = "Other"
                category = "Other"
                # Search in all trees
                found = False
                for r_type in self.trees:
                    for cat, items in self.trees[r_type].items():
                        if self._file_in_category(md_file.name, items):
                            category = cat
                            found = True
                            break
                    if found: break
                repo = self.file_repo_map.get(md_file.name, "")
                repo_type = self.repo_type_map.get(repo, "other")
                tags = self.file_tags_map.get(md_file.name, [])
                files_data.append({
                    "path": md_file.name,
                    "title": title,
                    "category": category,
                    "repo": repo,
                    "type": repo_type,
                    "tags": tags,
                    "summary": summary
                })
            except Exception as e:
                print(f"Warning: Could not process {md_file.name} for web index: {e}")
        index_data = {
            "files": files_data,
            "categories": list(self.categories.keys()),
            "repos": list(set(self.file_repo_map.values())),
            "types": list(set(self.repo_type_map.values()))
        }
        with open(self.output_dir / "docs_index.json", 'w', encoding='utf-8') as f:
            json.dump(index_data, f, indent=2)

        # Write dependencies graph
        with open(self.output_dir / "dependencies.json", 'w', encoding='utf-8') as f:
            json.dump(self.dependencies_map, f, indent=2)

    def _file_in_category(self, filename, items):
        for key, value in items.items():
            if isinstance(value, str) and filename in value:
                return True
            elif isinstance(value, dict):
                if self._file_in_category(filename, value):
                    return True
        return False

    # -------------------------------------------------------------------
    # Merge tiny files into a single "miscellaneous.md"
    # -------------------------------------------------------------------
    def merge_small_files(self, size_threshold=1024, whitelist_categories=None, misc_filename="miscellaneous.md"):
        if whitelist_categories is None:
            whitelist_categories = ['Controllers', 'Entities', 'Services', 'Repositories', 'Commands', 'Events', 'Plugins']
        misc_path = self.output_dir / misc_filename
        merged_content = []
        merged_files = []
        for md_file in list(self.output_dir.glob('*.md')):
            if md_file.name in ["SUMMARY.md", misc_filename]:
                continue
            # Determine category for this file
            category = "Other"
            category = "Other"
            # Search in all trees
            found = False
            for r_type in self.trees:
                for cat, items in self.trees[r_type].items():
                    if self._file_in_category(md_file.name, items):
                        category = cat
                        found = True
                        break
                if found: break
            # Skip files that belong to whitelist categories
            if category in whitelist_categories:
                continue
            # Check size
            if md_file.stat().st_size <= size_threshold:
                # Append its content with a header indicating original file
                with open(md_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                header = f"# {md_file.stem} (from {self.file_repo_map.get(md_file.name, '')})\n\n"
                merged_content.append(header + content)
                merged_files.append(md_file.name)
                # Remove from tree so it won't appear separately
                for r_type in self.trees:
                    for cat_items in self.trees[r_type].values():
                        for key, val in list(cat_items.items()):
                            if isinstance(val, str) and val.endswith(md_file.name):
                                del cat_items[key]
                md_file.unlink()
        if merged_content:
            with open(misc_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(merged_content))
            # Add misc file to tree under "Other"
            self.add_to_tree([misc_filename], f"[{misc_filename}]({misc_filename})", "Other", "other")
            self.file_repo_map[misc_filename] = "merged"


def deploy_viewer_assets(output_dir, assets_dir="viewer_assets"):
    """Copy the interactive viewer bundle into the MkDocs docs folder."""
    assets_path = Path(assets_dir)
    destination = Path(output_dir)
    if not assets_path.exists():
        print(f"[Viewer] Skipped: '{assets_dir}' folder not found.")
        return
    for root, dirs, files in os.walk(assets_path):
        rel_path = Path(root).relative_to(assets_path)
        target_dir = destination / rel_path
        target_dir.mkdir(parents=True, exist_ok=True)
        for file in files:
            src = Path(root) / file
            dst = target_dir / file
            shutil.copy2(src, dst)
    print(f"[Viewer] Assets copied to {destination}")

# ---------------------------------------------------------------------------
# Main driver – now supports multiple repositories
# ---------------------------------------------------------------------------
def main():
    # Add Git to PATH if not found (fix for Windows environment issue)
    # Add Git to PATH if not found (fix for Windows environment issue)
    if os.name == 'nt':
        git_path = r"C:\Program Files\Git\cmd"
        if git_path not in os.environ['PATH']:
            os.environ['PATH'] += os.pathsep + git_path

    # Load Config
    try:
        config = ConfigLoader.load('config.yaml')
    except FileNotFoundError:
        print("config.yaml not found.")
        sys.exit(1)

    # Initialize AI Enhancer
    ai_config = config.get('ai_enhancement', {})
    ai_enhancer = AIDocumentationEnhancer(ai_config)

    # Determine repositories to process
    repos_cfg = config.get('repositories', [])  # list of dicts with name, url, local_path
    if not repos_cfg:
        # Fallback to single repo (legacy behaviour)
        repo_dir = config.get('local_path', './repo_src')
        repos_cfg = [{"name": "main", "url": config.get('repo_url'), "local_path": repo_dir}]

    # Prepare output directory - preserve viewer assets
    output_dir = config['output_dir']
    if os.path.exists(output_dir):
        try:
            # Delete only markdown and JSON files, preserve viewer assets
            for item in os.listdir(output_dir):
                item_path = os.path.join(output_dir, item)
                # Preserve viewer, assets, javascripts, stylesheets folders
                if os.path.isdir(item_path) and item in ['viewer', 'assets', 'javascripts', 'stylesheets']:
                    print(f"[Preserve] Keeping {item} folder")
                    continue
                # Delete markdown and JSON files
                # Incremental Generation: Disable cleanup to preserve existing files
                # if os.path.isfile(item_path) and (item.endswith('.md') or item.endswith('.json')):
                #     os.remove(item_path)
                #     print(f"[Cleanup] Removed {item}")
        except PermissionError:
            print(f"Warning: Could not clean {output_dir} due to permission error. Continuing.")
    os.makedirs(output_dir, exist_ok=True)

    # Initialize generator
    generator = MarkdownGenerator(output_dir, ai_enhancer)
    generator.functional_scopes = config.get('functional_scopes', {})
    exclude_patterns = config.get('exclude', [])

    # Initialize parsers
    parsers = {
        '.php': PHPParser(),
        '.js': JSParser(),
        '.jsx': JSParser(),
        '.ts': TypeScriptParser(),
        '.tsx': TypeScriptParser(),
        '.vue': VueParser(),
        '.md': MDXParser(),
        '.mdx': MDXParser(),
        '.feature': GherkinParser(),
        '.twig': GenericParser(),
        '.json': GenericParser(),
        '.yaml': GenericParser(),
        '.yml': GenericParser(),
        '.xml': GenericParser(),
        '.css': GenericParser(),
        '.html': GenericParser(),
        '.neon': GenericParser(),
        '.sh': GenericParser(),
        '.bash': GenericParser(),
        'Dockerfile': GenericParser()
    }

    # Process each repository
    # -------------------------------------------------------------------------
    # Pass 1: Scan all files to build Class Map (for linking)
    # -------------------------------------------------------------------------
    all_files_to_process = [] # List of (file_path, info, content, local_path, name)
    
    for repo in repos_cfg:
        name = repo.get('name') or repo.get('url', '').split('/')[-1].replace('.git', '')
        if not name: name = "main"
        
        # Determine local path
        local_path = repo.get('local_path') or os.path.join('repo_src', name)
        repo_path = Path(local_path)
        repo_type = repo.get('type', 'other')
        generator.register_repo_type(name, repo_type)
        
        # Clone/Setup if needed
        token = os.environ.get('GITHUB_TOKEN')
        if repo.get('url'):
            manager = RepoManager(name, repo.get('url'), local_path, token)
            manager.setup()
        
        if not repo_path.exists():
            print(f"Repository path not found: {repo_path}")
            continue
            
        print(f"Scanning repository {name}...")
        
        for root, dirs, files in os.walk(repo_path):
            dirs[:] = [d for d in dirs if d not in exclude_patterns]
            
            for file in files:
                file_path = Path(root) / file
                if any(pat in str(file_path) for pat in exclude_patterns):
                    continue
                    
                ext = file_path.suffix
                parser = None
                if file == 'Dockerfile' or file.endswith('.dockerfile'):
                    parser = parsers.get('Dockerfile')
                elif ext in parsers:
                    parser = parsers.get(ext)
                elif ext == '.json' and file == 'package.json':
                     parser = parsers.get('.json')
                
                if parser:
                    try:
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                        
                        info = parser.parse(content)
                        all_files_to_process.append((file_path, info, content, repo_path, name))
                        
                        # Populate class map
                        stem = file_path.stem
                        rel_path = file_path.relative_to(repo_path)
                        safe_name = str(rel_path).replace(os.sep, '_').replace('.', '_') + '.md'
                        
                        generator.class_to_path_map[stem] = safe_name
                        generator.class_to_path_map[stem.lower()] = safe_name
                        
                        if 'classes' in info:
                            for cls in info['classes']:
                                generator.class_to_path_map[cls] = safe_name
                                generator.class_to_path_map[cls.lower()] = safe_name
                                
                    except Exception as e:
                        print(f"Error scanning {file_path}: {e}")

    # -------------------------------------------------------------------------
    # Pass 2: Generate Documentation
    # -------------------------------------------------------------------------
    for file_path, info, content, repo_path, repo_name in all_files_to_process:
        try:
            generator.generate(file_path, info, repo_path, repo_name, content)
        except Exception as e:
            print(f"Error generating {file_path}: {e}")

    # Write navigation and web index
    generator.write_index()
    generator.write_web_index()
    deploy_viewer_assets(output_dir)
    print(f"\n[SUCCESS] Documentation generated in {output_dir}")

if __name__ == "__main__":
    main()
