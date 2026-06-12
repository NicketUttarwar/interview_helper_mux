
Common issue. Perform this then follow steps for new build.


Install native arm64 Node (recommended: Homebrew)
On Apple Silicon, Homebrew should live at /opt/homebrew:

# Verify brew is arm64
which brew
# expect: /opt/homebrew/bin/brew
brew reinstall node@20
brew link --overwrite --force node@20
brew unlink node@20 && brew link node@20
Ensure Homebrew’s bin is before any old x64 paths in your shell:

echo 'export PATH="/opt/homebrew/opt/node@20/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
Then verify:


hash -r
which node
file "$(which node)"
node -p process.arch   # must print: arm64









------------------------------------------------------
Usually works upto here but below are additional optional fixes

------------------------------------------------------


If you use nvm, fnm, or asdf
Those often keep an old x64 Node selected.

nvm example:

nvm uninstall <old-version>   # optional, if x64
arch -arm64 zsh               # ensure arm64 shell
nvm install 20
nvm use 20
node -p process.arch          # arm64
fnm / asdf: reinstall Node 20 while in a native arm64 terminal (not Rosetta).



If Node still shows x64
Something earlier on PATH is winning. Find it:

type -a node
echo $PATH
Common culprits:

Path	Issue
/usr/local/bin/node
Intel Homebrew or old x64 installer
~/.nvm/...
x64 Node version still active
/usr/bin/node
Old system node (rare on modern macOS)
Fix: remove or deprioritize the x64 install, then reopen the terminal and recheck node -p process.arch.
