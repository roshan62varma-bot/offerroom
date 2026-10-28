"""Skill taxonomy and extraction.

Each skill has a canonical name, a category and aliases. Aliases starting with
"=" are matched case-sensitively, for words that are also plain English
("Go", "R", "Express").
"""

from __future__ import annotations

import re
from functools import lru_cache

_TAXONOMY = """
language: Python | py ; Java ; JavaScript | js | es6 ; TypeScript | ts ; C++ | cpp ; C | c programming | c language | =C/C++ | =C, C++ ; C# | csharp ;
  Go | golang | =Go ; Rust ; Kotlin ; Swift | =Swift ; Dart ; Ruby ; PHP ; Scala ; R | r programming | r language | rstudio | =Python/R | =R/Python ; SQL ;
  Bash | shell scripting | shell ; HTML | html5 ; CSS | css3 ; Solidity ; MATLAB
frontend: React | react.js | reactjs ; Next.js | nextjs ; Vue | vue.js | vuejs ; Angular | angularjs ;
  Svelte ; Redux ; Tailwind CSS | tailwind | tailwindcss ; Bootstrap ; jQuery ; Vite ; Webpack ;
  React Native | react-native ; Flutter ; Three.js
backend: Node.js | =Node | nodejs ; Express | express.js | expressjs | =Express ; Django ; Flask ; FastAPI ;
  Spring Boot | spring framework ; NestJS ; .NET | dotnet | asp.net ; Ruby on Rails | rails ; Laravel ;
  Celery
database: PostgreSQL | postgres | postgresql ; MySQL ; MongoDB | mongo ; Redis ; SQLite ; Firebase ;
  Supabase ; DynamoDB ; Cassandra ; Elasticsearch ; Prisma ; Kafka | apache kafka ; RabbitMQ
cloud: AWS | amazon web services ; GCP | google cloud ; Azure ; Docker ; Kubernetes | k8s ; Terraform ;
  CI/CD | ci cd | continuous integration ; GitHub Actions ; Jenkins ; Linux ; Nginx ; Vercel ;
  Serverless | lambda ; Ansible ; Prometheus ; Grafana
data: Machine Learning | ml | machine-learning ; Deep Learning ; PyTorch ; TensorFlow ; Keras ;
  scikit-learn | sklearn ; Pandas ; NumPy ; Data Analysis ; Data Visualization ; Matplotlib ;
  NLP | natural language processing ; Computer Vision | opencv ; LLMs | llm | large language models ;
  LangChain ; RAG | retrieval augmented generation ; Hugging Face | huggingface | transformers ;
  Spark | apache spark | pyspark ; Airflow ; Power BI ; Tableau ; Excel | =Excel | microsoft excel | ms excel ; Statistics ; Jupyter
tools: Git ; GitHub ; Postman ; Figma ; Jira ; VS Code ; Unity ; Selenium ; Playwright ; Jest ;
  Pytest ; Cypress ; JUnit
concept: Data Structures | dsa | data structures and algorithms ; Algorithms ; OOP | object oriented |
  object-oriented programming ; System Design ; DBMS ; Operating Systems ; Computer Networks |
  networking ; Unit Testing | testing ; Agile | scrum ; API Design ; Security | cybersecurity ;
  Web3 | blockchain ; Open Source ; GraphQL ; REST APIs | restful | rest api | rest apis | restful apis ; gRPC ;
  WebSockets | websocket ; Microservices | microservice
soft: Communication ; Teamwork | collaboration ; Problem Solving | problem-solving ; Leadership
"""


def _parse() -> dict[str, tuple[str, list[str]]]:
    skills: dict[str, tuple[str, list[str]]] = {}
    category = ""
    for chunk in re.split(r";|\n", _TAXONOMY):
        chunk = chunk.strip()
        if not chunk:
            continue
        m = re.match(r"^([a-z]+):\s*(.*)$", chunk)
        if m:
            category, chunk = m.group(1), m.group(2)
        names = [n.strip() for n in chunk.split("|") if n.strip()]
        if names:
            skills[names[0]] = (category, names)
    return skills


SKILLS = _parse()


@lru_cache(maxsize=1)
def _patterns() -> list[tuple[str, re.Pattern]]:
    out = []
    for canon, (_, aliases) in SKILLS.items():
        for alias in aliases:
            sensitive = alias.startswith("=")
            alias = alias.lstrip("=")
            if len(alias) == 1:
                continue  # "C", "R": too ambiguous alone; matched via their longer aliases
            if not sensitive and "=" + alias in aliases:
                continue  # an everyday word ("go", "swift"): only the capitalized form counts
            body = re.escape(alias).replace(r"\ ", r"[\s\-]+")
            pat = re.compile(rf"(?<![A-Za-z0-9+#.]){body}(?![A-Za-z0-9+#])", 0 if sensitive else re.I)
            out.append((canon, pat))
    return out


def extract(text: str) -> list[str]:
    """Canonical skills mentioned in text, in order of first appearance."""
    hits: dict[str, int] = {}
    for canon, pat in _patterns():
        m = pat.search(text)
        if m and (canon not in hits or m.start() < hits[canon]):
            hits[canon] = m.start()
    # "React Native" also matches "React"; only keep React if it appears on its own
    if "React Native" in hits and "React" in hits:
        if not re.search(r"(?<![A-Za-z])React(?![\s\-]*Native)", text, re.I):
            del hits["React"]
    return sorted(hits, key=hits.get)


# Having the left skill is evidence of the right one ("Pytest" means you've done unit testing).
IMPLIES = {
    "Pytest": ["Unit Testing"], "Jest": ["Unit Testing"], "JUnit": ["Unit Testing"],
    "Cypress": ["Unit Testing"], "Playwright": ["Unit Testing"],
    "PostgreSQL": ["SQL"], "MySQL": ["SQL"], "SQLite": ["SQL"],
    "FastAPI": ["REST APIs"], "Django": ["REST APIs"], "Flask": ["REST APIs"], "Express": ["REST APIs"],
    "Spring Boot": ["REST APIs", "Java"], "Next.js": ["React"], "TypeScript": ["JavaScript"],
    "GitHub Actions": ["CI/CD"], "Jenkins": ["CI/CD"], "GitHub": ["Git"],
}


def canonical(name: str) -> str:
    """Map a free-text skill ("k8s", "ReactJS") to its canonical name, or keep it."""
    found = extract(name)
    return found[0] if len(found) == 1 else name.strip()


def category(skill: str) -> str:
    return SKILLS.get(skill, ("other", []))[0]


# Bite-sized ways to close a gap, used by fit reports.
GAP_PROJECTS = {
    "Docker": "Containerize one of your existing projects and add a docker-compose.yml with its database.",
    "Kubernetes": "Deploy your Dockerized project to a local kind/minikube cluster with a Deployment + Service.",
    "AWS": "Host a project on AWS free tier (EC2 or Lambda + S3) and write down the architecture in the README.",
    "GCP": "Deploy a small API to Cloud Run and connect it to a managed database.",
    "Azure": "Deploy a small API to Azure App Service with a GitHub Actions pipeline.",
    "CI/CD": "Add a GitHub Actions workflow that runs tests and lints on every push to one project.",
    "GitHub Actions": "Add a workflow that runs your tests and builds a release on tags.",
    "TypeScript": "Port a small JavaScript project to TypeScript with strict mode on.",
    "React": "Build a React dashboard that consumes one of your own APIs.",
    "Next.js": "Rebuild a portfolio or project front-end in Next.js with server-side rendering.",
    "Node.js": "Write a REST API in Node.js + Express with auth and tests.",
    "PostgreSQL": "Swap a project's storage to PostgreSQL, with migrations and indexes on hot queries.",
    "MongoDB": "Add a MongoDB-backed feature (e.g. activity feed) to an existing project.",
    "Redis": "Add Redis caching or rate limiting to one of your APIs and measure the speed-up.",
    "GraphQL": "Expose an existing REST API through a small GraphQL layer.",
    "System Design": "Write a one-page design doc for scaling one of your projects to 10x users.",
    "Data Structures": "Solve 30 curated problems (arrays, hashing, trees, graphs) and log patterns learned.",
    "Algorithms": "Pin your LeetCode/Codeforces profile and write up 3 problems (approach, complexity) in a repo.",
    "MySQL": "Port one project's PostgreSQL schema to MySQL and note the differences in the README.",
    "TypeScript": "Port a small JavaScript project to TypeScript with strict mode on.",
    "Elasticsearch": "Add full-text search to a project with Elasticsearch (or OpenSearch) running in Docker.",
    "Machine Learning": "Train and evaluate a baseline model on a public dataset; report metrics honestly.",
    "PyTorch": "Re-implement a small model (e.g. MNIST CNN) in PyTorch with a training loop you wrote.",
    "LLMs": "Build a small RAG app over your own notes and evaluate answer quality on 20 questions.",
    "FastAPI": "Build a FastAPI service with typed models, auth and auto-generated docs.",
    "Django": "Build a Django app with an admin panel and deploy it.",
    "Unit Testing": "Add tests to an existing project until the core logic is covered; add a coverage badge.",
    "Linux": "Do your next project's deployment by hand on a Linux VM (ssh, systemd, nginx).",
    "Microservices": "Split one project into two services that talk over HTTP or a queue.",
    "Kafka": "Add an event stream between two services with Kafka (or Redpanda locally).",
    "Figma": "Design the next feature of a project in Figma before building it; link the file.",
}


def gap_project(skill: str) -> str:
    return GAP_PROJECTS.get(skill, f"Build a small, finished project that uses {skill} and link it on your resume.")
