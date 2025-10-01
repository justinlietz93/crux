# Crux Providers Documentation

Welcome to the Crux Providers documentation directory. This folder contains comprehensive guides for setting up, testing, and troubleshooting the Crux Providers system.

---

## Documentation Index

### 🚀 Getting Started

#### [SETUP_GUIDE.md](./SETUP_GUIDE.md) - **START HERE**
Complete setup and installation guide for new users.

**Contents:**
- Prerequisites and system requirements
- Step-by-step installation instructions
- Virtual environment setup
- Configuration guide
- Project structure explained
- Usage examples
- Common issues and solutions

**Use this if:**
- You're setting up Crux Providers for the first time
- You're confused about the project structure
- You need to understand the architecture
- You're getting import errors or dependency issues

---

### 🧪 Testing

#### [BETA_TESTING_CHECKLIST.md](./BETA_TESTING_CHECKLIST.md)
Comprehensive testing checklist for beta testers and QA.

**Contents:**
- Environment setup validation
- Installation verification
- Configuration testing
- Provider-specific tests (all 7 providers)
- Ollama-specific testing procedures
- Architecture compliance checks
- Integration testing scenarios
- Performance and security validation
- Testing report template

**Use this if:**
- You're beta testing the system
- You need to validate a new installation
- You're running QA before deployment
- You need a structured testing approach

---

### 🔧 Troubleshooting

#### [OLLAMA_ISSUES.md](./OLLAMA_ISSUES.md)
Detailed troubleshooting guide for Ollama provider issues.

**Contents:**
- Known Issue #1: Model fetching reliability
- Known Issue #2: Executable not found
- Known Issue #3: Service not running
- Known Issue #4: Permission errors
- Known Issue #5: No models available
- Diagnostic commands
- Advanced troubleshooting
- Workarounds
- Issue reporting template

**Use this if:**
- Ollama model fetching is failing
- You're getting "executable not found" errors
- You need to debug Ollama-specific problems
- You want to understand the fallback behavior

---

### 📚 Additional Documentation

#### [MemoriPilot.md](./MemoriPilot.md)
Documentation for the MemoriPilot memory management system.

#### [Jupyter-Notebook.md](./Jupyter-Notebook.md)
Guide for using Crux Providers in Jupyter notebooks.

#### [Github-dlr.md](./Github-dlr.md)
Information about GitHub DLR (Download) utilities.

---

## Quick Navigation

### I want to...

**...set up the project for the first time**
→ Read [SETUP_GUIDE.md](./SETUP_GUIDE.md)

**...test the system thoroughly**
→ Follow [BETA_TESTING_CHECKLIST.md](./BETA_TESTING_CHECKLIST.md)

**...fix Ollama issues**
→ Check [OLLAMA_ISSUES.md](./OLLAMA_ISSUES.md)

**...understand the architecture**
→ See [SETUP_GUIDE.md](./SETUP_GUIDE.md) "Project Structure Explained" section
→ Also read `../ARCHITECTURE_RULES.md` in the repository root

**...contribute code**
→ Read `../crux_providers/README.md` for contribution guidelines
→ Review `../ARCHITECTURE_RULES.md` for architectural constraints

**...run tests**
→ See "Running Tests" section in [SETUP_GUIDE.md](./SETUP_GUIDE.md)
→ Use [BETA_TESTING_CHECKLIST.md](./BETA_TESTING_CHECKLIST.md) for comprehensive testing

**...report a bug**
→ Use issue template in [OLLAMA_ISSUES.md](./OLLAMA_ISSUES.md) for Ollama issues
→ Use template in [BETA_TESTING_CHECKLIST.md](./BETA_TESTING_CHECKLIST.md) for general issues

---

## Document Summary

| Document | Purpose | Length | Target Audience |
|----------|---------|--------|----------------|
| [SETUP_GUIDE.md](./SETUP_GUIDE.md) | Setup & installation | ~500 lines | New users, developers |
| [BETA_TESTING_CHECKLIST.md](./BETA_TESTING_CHECKLIST.md) | Testing procedures | ~700 lines | Beta testers, QA |
| [OLLAMA_ISSUES.md](./OLLAMA_ISSUES.md) | Ollama troubleshooting | ~600 lines | Users with Ollama issues |
| [MemoriPilot.md](./MemoriPilot.md) | Memory management | - | Advanced users |
| [Jupyter-Notebook.md](./Jupyter-Notebook.md) | Jupyter integration | - | Data scientists |
| [Github-dlr.md](./Github-dlr.md) | GitHub utilities | - | Developers |

---

## Quick Start

If you're completely new to Crux Providers, follow this sequence:

1. **Read:** [SETUP_GUIDE.md](./SETUP_GUIDE.md) - "Overview" section
2. **Do:** Follow "Installation" section in [SETUP_GUIDE.md](./SETUP_GUIDE.md)
3. **Verify:** Run "Quick Reference Commands" at the end of [SETUP_GUIDE.md](./SETUP_GUIDE.md)
4. **If Ollama issues:** Consult [OLLAMA_ISSUES.md](./OLLAMA_ISSUES.md)
5. **For testing:** Use [BETA_TESTING_CHECKLIST.md](./BETA_TESTING_CHECKLIST.md)

---

## Related Documentation

- **Architecture:** `../ARCHITECTURE_RULES.md` - Architectural guidelines and constraints
- **Agents:** `../AGENTS.md` - Instructions for AI agents
- **Provider README:** `../crux_providers/README.md` - Developer documentation
- **System Instructions:** `../providers-system-instructions.md` - Provider implementation guidelines

---

## Feedback

Found an issue with the documentation? Please:
1. Check if the issue is already covered in [OLLAMA_ISSUES.md](./OLLAMA_ISSUES.md)
2. Create a GitHub issue with `[DOCS]` prefix
3. Include document name and section

---

## Updates

**Last Updated:** 2025-01-01
**Version:** 1.0

These documents are actively maintained. Check the repository for the latest versions.

---

**Navigation:** [← Back to Repository](../) | [Setup Guide →](./SETUP_GUIDE.md)
