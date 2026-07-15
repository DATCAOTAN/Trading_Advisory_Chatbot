# Docker Workflow

## Normal Local Start

```powershell
docker-compose up -d
```

## Ordinary Python or UI Source Changes

Use:

```powershell
docker-compose restart app
```

Do not rebuild the app container for ordinary Python source changes.

## When Rebuild Is Appropriate

Rebuild only when Dockerfile, dependency files, or image-level system dependencies changed.

Avoid:

```powershell
docker-compose up -d --build --force-recreate app
```

unless a Dockerfile or dependency change truly requires it.

## Configuration Check

```powershell
docker-compose config
```

This validates Compose configuration without rebuilding.
