"""Reject generated artifacts in the main source repository (submodule stays pinned)."""
from pathlib import Path,PurePosixPath
import subprocess

from official_release import FORBIDDEN_PARTS,FORBIDDEN_SUFFIXES

ROOT=Path(__file__).resolve().parents[1]


def violations(paths):
    issues=[]
    for name in paths:
        path=PurePosixPath(name)
        if not name or name=='kotaemon':continue
        if path.parts[0] in {'output','playwright-report','test-results'} or FORBIDDEN_PARTS.intersection(path.parts):
            issues.append(name)
        elif path.suffix.lower() in FORBIDDEN_SUFFIXES or any(part.endswith('.egg-info') for part in path.parts):
            issues.append(name)
        elif path.name=='.env' or path.name.startswith('.env.') and path.name!='.env.example':
            issues.append(name)
    return issues


if __name__=='__main__':
    paths=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT,text=True).split('\0')
    issues=violations(paths)
    if issues:raise SystemExit('Remove generated/private tracked files:\n'+'\n'.join(issues))
    print('Repository artifact check passed')
