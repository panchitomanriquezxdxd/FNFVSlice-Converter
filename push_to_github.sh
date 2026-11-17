#!/usr/bin/env bash
# Sube este proyecto a tu repo. Requiere git y tener sesión iniciada en GitHub (gh auth login o token).
set -e
git init
git add .
git commit -m "Initial commit: Psych/Codename -> V-Slice converter with AI analysis"
git branch -M main
git remote add origin https://github.com/panchitomanriquezxdxd/FNFVSlice-Converter.git
git push -u origin main
