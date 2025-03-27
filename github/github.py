import re
import aiohttp
from typing import Dict, List, Optional, Union
from uagents import Model
from uagents.models import Field

GITHUB_API_BASE = "https://api.github.com/"
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
GITHUB_TOKEN = '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'  
GEMINI_API_KEY = 'AIzaSyDxxSzqkL24eW3nSCjNyyM9CaydBtBqfTA'  

class RepoRequest(Model):
    repo_url: str = Field(
        description="GitHub repository URL",
    )

class RepoAnalysis(Model):
    name: str = Field(description="Repository name in the format owner/repo")
    commit_count: int = Field(description="Number of commits in the repository")
    file_count: int = Field(description="Number of code files analyzed")
    imported_modules: List[str] = Field(description="List of imported modules")
    dependencies: List[str] = Field(description="List of dependencies from requirements.txt")
    apis: List[str] = Field(description="List of detected APIs")
    functions: List[str] = Field(description="List of extracted functions")
    classes: List[str] = Field(description="List of extracted class names")
    gemini_analysis: str = Field(description="Detailed analysis from Gemini API")

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "commit_count": self.commit_count,
            "file_count": self.file_count,
            "imported_modules": self.imported_modules,
            "dependencies": self.dependencies,
            "apis": self.apis,
            "functions": self.functions,
            "classes": self.classes,
            "gemini_analysis": self.gemini_analysis
        }

async def fetch_repo_contents(session: aiohttp.ClientSession, repo_owner: str, repo_name: str, path: str = "") -> List[Dict]:
    """Recursively fetch all contents of a GitHub repository asynchronously."""
    url = f"{GITHUB_API_BASE}repos/{repo_owner}/{repo_name}/contents/{path}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    
    async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
        if response.status != 200:
            raise Exception(f"Failed to fetch contents: {response.status} - {await response.text()}")
        contents = await response.json()
    
    all_contents = []
    
    for item in contents:
        all_contents.append(item)
        if item["type"] == "dir":
            sub_contents = await fetch_repo_contents(session, repo_owner, repo_name, item["path"])
            all_contents.extend(sub_contents)
    
    return all_contents

def extract_classes(code: str) -> List[str]:
    """Extract class names from Python code."""
    class_pattern = r"class\s+(\w+)\s*(?:\(|:)"
    return re.findall(class_pattern, code)

def extract_comments(code: str) -> List[str]:
    """Extract comments from code."""
    comment_pattern = r"#.*$|\"\"\"[\s\S]*?\"\"\"|'''[\s\S]*?'''"
    return re.findall(comment_pattern, code, re.MULTILINE)

async def analyze_github_repo(request: Union[RepoRequest, str]) -> Dict:
    """Analyze a GitHub repository asynchronously and return a detailed summary."""
    # Initialize RepoAnalysis with minimal defaults
    analysis = RepoAnalysis(
        name="",
        commit_count=0,
        file_count=0,
        imported_modules=[],
        dependencies=[],
        apis=[],
        functions=[],
        classes=[],
        gemini_analysis=""
    )
    
    # Extract repo URL, handling both RepoRequest and string inputs
    if isinstance(request, RepoRequest):
        repo_url = request.repo_url
    elif isinstance(request, str):
        repo_url = request
    else:
        return {"error": "Invalid input: Expected a RepoRequest object or a string URL"}
    
    repo_path = repo_url.replace("https://github.com/", "").strip("/")
    try:
        repo_owner, repo_name = repo_path.split('/')
    except ValueError:
        return {"error": "Invalid repository URL format. Expected: https://github.com/owner/repo"}
    
    analysis.name = f"{repo_owner}/{repo_name}"
    
    async with aiohttp.ClientSession() as session:
        commits_url = f"{GITHUB_API_BASE}repos/{repo_owner}/{repo_name}/commits"
        headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
        async with session.get(commits_url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as commits_response:
            analysis.commit_count = len(await commits_response.json()) if commits_response.status == 200 else 0
        
        # Fetch all repository contents recursively
        try:
            contents = await fetch_repo_contents(session, repo_owner, repo_name)
        except Exception as e:
            return {"error": str(e)}
        
        code_files = []
        all_code_content = []
        requirements_content = None
      
        for item in contents:
            if item["type"] == "file":
                if item["name"].endswith((".py", ".js", ".ts", ".java", ".cpp", ".html", ".css", ".json", ".md")):
                    file_url = item["download_url"]
                    async with session.get(file_url, timeout=aiohttp.ClientTimeout(total=10)) as file_response:
                        if file_response.status == 200:
                            code_files.append({"name": item["name"], "content": await file_response.text()})
                elif item["name"].lower() == "requirements.txt":
                    file_url = item["download_url"]
                    async with session.get(file_url, timeout=aiohttp.ClientTimeout(total=10)) as file_response:
                        if file_response.status == 200:
                            requirements_content = await file_response.text()
        
        analysis.file_count = len(code_files)
        
        # Analyze code files
        imported_modules_set = set()
        dependencies_set = set()
        apis_set = set()
        functions_set = set()
        classes_set = set()
        
        for file in code_files:
            code = file["content"]
            file_ext = file["name"].split('.')[-1]
            all_code_content.append(f"## {file['name']}\n\n```{file_ext}\n{code}\n```\n\n")
            
            # Extract imports (Python-specific)
            if file["name"].endswith(".py"):
                import_pattern = r"^(?:import|from)\s+([a-zA-Z0-9_]+(?:\.[a-zA-Z0-9_]+)*)(?:\s+import|\s+as|\s*$)"
                imports = set(re.findall(import_pattern, code, re.MULTILINE))
                imported_modules_set.update(imports)
            
            # Extract dependencies from requirements.txt
            if requirements_content:
                for line in requirements_content.splitlines():
                    line = line.strip().lower()
                    if line and not line.startswith('#'):
                        package = re.split('==|>=|<=', line)[0].strip()
                        dependencies_set.add(package)
            
            # Detect API calls
            if any(api_call in code for api_call in ["requests.get", "requests.post", "fetch", "axios"]):
                apis_set.add("HTTP API calls detected")
            
            # Extract functions (Python-specific)
            if file["name"].endswith(".py"):
                func_matches = re.findall(r"def\s+(\w+)\s*\(", code)
                functions_set.update(func_matches)
            
            # Extract classes (Python-specific)
            if file["name"].endswith(".py"):
                class_matches = extract_classes(code)
                classes_set.update(class_matches)
        
        analysis.imported_modules = sorted(imported_modules_set)
        analysis.dependencies = sorted(dependencies_set)
        analysis.apis = sorted(apis_set)
        analysis.functions = sorted(functions_set)
        analysis.classes = sorted(classes_set)
        
        if not all_code_content:
            return {"error": "No relevant code files found in the repository"}
        combined_code = (
            f"Repository: {analysis.name}\n"
            f"Commit Count: {analysis.commit_count}\n"
            f"File Count: {analysis.file_count}\n"
            f"Imported Modules: {', '.join(analysis.imported_modules)}\n"
            f"Dependencies (from requirements.txt): {', '.join(analysis.dependencies) if analysis.dependencies else 'None found'}\n"
            f"APIs Detected: {', '.join(analysis.apis)}\n"
            f"Functions: {', '.join(analysis.functions)}\n"
            f"Classes: {', '.join(analysis.classes)}\n\n"
            + "\n".join(all_code_content)
        )
      
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{
                "parts": [{
                    "text": (
                        f"Provide a detailed analysis of the GitHub repository '{analysis.name}' from Fetch.ai. Use the following content, which includes all files, their code, and extracted metadata:\n\n"
                        f"{combined_code}\n\n"
                        "Your analysis must include:\n"
                        "1. **Purpose and Functionality**: Describe the overall goal of the repository, its intended use, and how it functions (e.g., types of agents, system architecture).\n"
                        "2. **Frameworks, APIs, and Key Components**: Identify all frameworks, libraries, APIs, key functions, and classes, explaining their roles.\n"
                        "3. **File-by-File Breakdown**: For each file, detail its purpose, contents (e.g., functions, classes, key logic), and how it contributes to the project.\n"
                        "4. **Code Quality and Structure**: Assess readability, maintainability, modularity, and adherence to best practices.\n"
                        "5. **Unique Features and Notable Details**: Highlight any standout features, innovative approaches, or important implementation details.\n"
                        "Ensure the analysis is comprehensive, specific, and covers all aspects of the repository."
                    )
                }]
            }]
        }
        async with session.post(
            GEMINI_API_URL.format(GEMINI_API_KEY=GEMINI_API_KEY),
            json=payload,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=120)  
        ) as gemini_response:
            if gemini_response.status == 200:
                analysis.gemini_analysis = (await gemini_response.json())["candidates"][0]["content"]["parts"][0]["text"]
            else:
                analysis.gemini_analysis = f"Gemini API error: {await gemini_response.text()}"
    
    return analysis.to_dict()
