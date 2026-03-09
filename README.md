# 🚀 Modernisation Platform UI

[![Ministry of Justice Repository Compliance Badge](https://github-community.service.justice.gov.uk/repository-standards/api/github-community/badge)](https://github-community.service.justice.gov.uk/repository-standards/modernisation-platform-ui) [![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/ministryofjustice/modernisation-platform-ui/badge)](https://scorecard.dev/viewer/?uri=github.com/ministryofjustice/modernisation-platform-ui)

[![Open in Dev Container](https://raw.githubusercontent.com/ministryofjustice/.devcontainer/refs/heads/main/contrib/badge.svg)](https://vscode.dev/redirect?url=vscode://ms-vscode-remote.remote-containers/cloneInVolume?url=https://github.com/ministryofjustice/modernisation-platform-ui) [![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/ministryofjustice/modernisation-platform-ui)

Welcome to the **Modernisation Platform UI**!

## 📜 Table of Contents

- [📣 About Modernisation Platform UI](#-about-modernisation-platform-ui)
- [📌 Projects](#-projects)
- [🏗️ modernisation-platform-ui Repository](#-modernisation-platform-ui-repository)
  - [🔑 Key Features](#-key-features)
  - [📂 Folder Structure](#-folder-structure)
  - [🌎 Hosted Services](#-hosted-services)
  - [✅ Benefits](#-benefits)
  - [❌ Challenges](#-challenges)
  - [🛠️ Development Setup](#-development-setup)
- [📄 License](#-license)

## 📣 About Modernisation Platform UI

The **Modernisation Platform UI** is an application hosted on the Cloud Platform and built by the Modernisation Platform Team to host various projects.


## 📌 Projects

The community currently provides the following projects and services:

| Project Name              | Description                                                                                               |
| ------------------------- | --------------------------------------------------------------------------------------------------------- |
| **Reports**               | View various reports and insights for the Modernisation Platform.                                         |
| **...**                   | More projects to be added...                                                                              |

## 🏗️ modernisation-platform-ui Repository

To help engineers quickly build and deploy their projects, this repository hosts a **modular monolithic Flask application**. Engineers can optionally choose to host their ideas here, minimising maintenance burdens while gaining quick access to shared components.

### 🔑 Key Features

- **Single Flask Application:** A shared core framework hosting multiple projects.
- **Single Set of Dependencies:** Simplified dependency management.
- **Shared Authentication:** Quickly secure projects with a common authentication layer.
- **Modular Code Structure:** Projects are self-contained within the monolith.

### 📂 Folder Structure

```
/modernisation-platform-ui/
├── app/                      # Core Flask application
│   └── projects/                 # Individual project modules
│       ├── reports/              # Reports project module
│       └── ...
│   └── shared/                   # Shared modules
│       ├── config/                   # Shared configuration settings
│       ├── middleware/               # Shared middleware functions
│       ├── routes/                   # Shared routes
│       └── ...
├── tests/                    # Automated tests
└── ...
```

### 🌎 Hosted Services

This repository provides a set of services accessible at **[modernisation-platform.cloud-platform.service.justice.gov.uk](https://modernisation-platform.cloud-platform.service.justice.gov.uk)**, including:

- **✅ Reports** – View various reports and insights for the Modernisation Platform.

### ✅ Benefits

- **Simplified Maintenance** – One codebase to manage.
- **Shared Components** – Reduces duplication of common functionality.
- **Easier Collaboration** – Community contributions are streamlined.
- **Scalable & Extensible** – New projects can be added with minimal setup.

### ❌ Challenges

- **Coupling** – Projects share infrastructure and dependencies.
- **Deployment Coordination** – Updates affect all projects simultaneously.
- **Performance Considerations** – Shared resources must be optimised.

### 🛠️ Development Setup

### Prerequisites

- [uv](https://docs.astral.sh/uv/)
- Docker

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
