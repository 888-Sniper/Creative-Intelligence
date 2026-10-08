# Creative Intelligence

Product repo. Path: `/Users/simrandhillon/orca/workspaces/Creative-Intelligence/daggertooth`  
Remote: `https://github.com/888-Sniper/Creative-Intelligence` (`main`)

`main` is checked out in `/Users/simrandhillon/Creative Intelligence/Creative-Intelligence`. Commit on the current branch, fast-forward that worktree, then `git push origin main`. Stop if that worktree is dirty or `origin/main` has moved.

## Audit prompt after every push

The owner asked on 2026-10-08 that this apply in every session. GitHub Gist is blocked for the other AI, so the prompt lives in this repo.

On every push to `origin main`, replace `Audit.md` in that same push. Do not create a new path and do not append. Do not use the gist.

Write it as the check for what that push puts on `main`: what should be true, and how to confirm it. The commit under review is `origin/main` after fetch. A behind local checkout, or no local `main` branch, is not a reason to stop. A history diff names both ends, `git diff --stat <parent> origin/main`. A one-revision diff uses the local checkout, so a behind checkout shows changes that are not in the push. Stop only if `origin/main` and GitHub `main` differ, or the worktree is dirty. Tell the other AI not to edit, commit, push, build, install, start the server, or activate a provider, and to report only defects that are still true, with file and line. Do not treat an unrun live model, live browser, or a previously stored analysis as a source defect.

The stable link is https://github.com/888-Sniper/Creative-Intelligence/blob/main/Audit.md
