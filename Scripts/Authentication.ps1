# (se non hai gh) – installa
winget install --id GitHub.cli -e

# login con scope repo + workflow
gh auth login -s "repo,workflow"

# configura git per usare il token di gh
gh auth setup-git

# verifica stato
gh auth status
