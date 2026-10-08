# Creative Intelligence audit for 2026-10-08

Review `origin/main` after `git fetch`. Confirm that `origin/main` and GitHub `main` name the same SHA. A behind local checkout or a missing local `main` branch is not a reason to stop; use `git show origin/main:PATH`. Stop only if the remote identities differ or the worktree is dirty.

This is the product repo https://github.com/888-Sniper/Creative-Intelligence. The parent of this push is `9e022f631d710a1848a000717feff8ea848d4cad` (`Bound English promotion cues to whole words`). This push adds the standing audit rule in `AGENTS.md` and replaces this file. It does not change analysis behavior. English promotion cues remain whole words (`app`, `shop`, `basket`, `buy`, `order`, `discount`, `off`, with a trailing `s` where that pattern allows). The stems `aplikac`, `košar`, `kosar`, `nakup`, `popust`, and `akcij` remain substrings. `Happy birthday` and `Meet our officer` stay `unknown`. Do not edit, commit, push, build, install, start the server, or activate a provider. Do not treat an unrun live model, live browser, or a previously stored analysis as a source defect. Report only defects still present at the reviewed SHA, with severity, observed behavior, file and line, and the evidence that reproduces them. State checks not performed.

## Standing audit rule

`AGENTS.md` tells every later session to replace repo-root `Audit.md` in the same push to `origin main`. The file is not appended, and it is not given a new path. The stable link is https://github.com/888-Sniper/Creative-Intelligence/blob/main/Audit.md. GitHub Gist is not used. The commit under review is `origin/main` after fetch. A behind local checkout is not a reason to stop. Stop only when `origin/main` and GitHub `main` differ, or the worktree is dirty.

`main` stays checked out in `/Users/simrandhillon/Creative Intelligence/Creative-Intelligence`. A change is committed on the working branch, fast-forwarded there, and pushed. A dirty main worktree, or an `origin/main` that has moved, stops the push.

Confirm `AGENTS.md` contains that rule. Confirm this push does not edit the pipeline:

```
git diff --stat 9e022f631d710a1848a000717feff8ea848d4cad
```

The diff is `AGENTS.md` and `Audit.md` only.
