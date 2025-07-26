#!/usr/bin/env bash

echo "📥 Cloning SEO blog repo..."
git clone https://github.com/owoicho09/seo-blog seo-blog

echo "📦 Installing Python dependencies..."
pip install -r requirements.txt

echo "🎭 Installing Playwright dependencies..."
python -m playwright install

echo "🧹 Collecting static files..."
python manage.py collectstatic --noinput
