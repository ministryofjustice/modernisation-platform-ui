# 🚀 Modernisation Platform UI

[![Ministry of Justice Repository Compliance Badge](https://github-community.service.justice.gov.uk/repository-standards/api/github-community/badge)](https://github-community.service.justice.gov.uk/repository-standards/github-community) [![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/ministryofjustice/github-community/badge)](https://scorecard.dev/viewer/?uri=github.com/ministryofjustice/github-community)

[![Open in Dev Container](https://raw.githubusercontent.com/ministryofjustice/.devcontainer/refs/heads/main/contrib/badge.svg)](https://vscode.dev/redirect?url=vscode://ms-vscode-remote.remote-containers/cloneInVolume?url=https://github.com/ministryofjustice/github-community) [![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/ministryofjustice/github-community)

Welcome to the **Modernisation Platform UI**!

## 📜 Table of Contents

- [📣 About GitHub Community](#-about-github-community)
- [📌 Projects](#-projects)
- [🏗️ github-community Repository](#-github-community-repository)
  - [🔑 Key Features](#-key-features)
  - [📂 Folder Structure](#-folder-structure)
  - [🌎 Hosted Services](#-hosted-services)
  - [✅ Benefits](#-benefits)
  - [❌ Challenges](#-challenges)
  - [🛠️ Development Setup](#-development-setup)
- [📄 License](#-license)

## 📣 About GitHub Community

The **GitHub Community** is a group of passionate engineers dedicated to building great services. It is run by volunteers and promotes an **engineer-first** approach, ensuring that projects remain in the hands of those who actively develop them. The community fosters innovation and collaboration by supporting multiple projects within the **Ministry of Justice** GitHub ecosystem.

## 📌 Projects

The community currently provides the following projects and services:

| Project Name              | Description                                                                                               |
| ------------------------- | --------------------------------------------------------------------------------------------------------- |
| **Repository Standards**  | Improving code quality and security by centralizing knowledge and best practices for GitHub repositories. |
| **Shared GitHub Actions** | Providing reusable GitHub Actions to reduce technical debt, improve maintainability, and enhance quality. |
| **...**                   | More projects to be added...                                                                              |

## 🏗️ github-community Repository

The **github-community repository** serves as the primary hub and a single pane of glass for all things **GitHub Community**. To help engineers quickly build and deploy their projects, this repository hosts a **modular monolithic Flask application**. Engineers can optionally choose to host their ideas here, minimizing maintenance burdens while gaining quick access to shared components.

### 🔑 Key Features

- **Single Flask Application:** A shared core framework hosting multiple projects.
- **Single Set of Dependencies:** Simplified dependency management.
- **Shared Database (Amazon RDS - PostgreSQL):** Minimal maintenance with easy access to data persistence.
- **Shared Authentication:** Quickly secure projects with a common authentication layer.
- **Modular Code Structure:** Projects are self-contained within the monolith.

### 📂 Folder Structure

```
/modernisation-platform-ui/
├── app/                      # Core Flask application
│   └── projects/                 # Individual project modules
│       ├── repository_standards/     # Repository standards module
│       ├── shared_github_actions/    # GitHub Actions module
│       └── ...
│   └── shared/                   # Shared modules
│       ├── config/                   # Shared configuration settings
│       ├── middleware/               # Shared middleware functions
│       ├── routes/                   # Shared routes
│       ├── database.py               # Shared database connection
│       └── ...
├── tests/                    # Automated tests
└── ...
```

### 🌎 Hosted Services

This repository provides a set of services accessible at **[github-community.service.justice.gov.uk](https://github-community.service.justice.gov.uk)**, including:

- **✅ Repository Standards** – Automated reports on repository health and best practices.

### ✅ Benefits

- **Simplified Maintenance** – One codebase to manage.
- **Shared Components** – Reduces duplication of common functionality.
- **Easier Collaboration** – Community contributions are streamlined.
- **Scalable & Extensible** – New projects can be added with minimal setup.

### ❌ Challenges

- **Coupling** – Projects share infrastructure and dependencies.
- **Deployment Coordination** – Updates affect all projects simultaneously.
- **Performance Considerations** – Shared resources must be optimized.

### 🛠️ Development Setup

### Prerequisites

- [uv](https://docs.astral.sh/uv/)
- Docker (optional for local database setup)

### Setup Instructions

```sh
# Clone the repository
git clone https://github.com/ministryofjustice/modernisation-platform-ui.git

cd modernisation-platform-ui

# Install dependencies
make uv-activate

# Run the application
make app-start
```

---

## 📄 License

This project is licensed under the **MIT License**. See the [LICENSE](LICENSE) file for details.
