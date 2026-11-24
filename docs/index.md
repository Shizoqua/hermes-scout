---
hide:
  - navigation
  - toc
---

<div class="sc-hero" markdown>

<img class="sc-logo" src="logo.svg" alt="">

# Ask your files anything.

<p class="sc-lead">Private search by meaning for your notes, docs, code, PDFs, Office and
OpenDocument files. For <a href="https://github.com/NousResearch/hermes-agent">Hermes Agent</a> and
any terminal.</p>

<div class="sc-install" markdown>

=== "Hermes plugin"

    ```bash
    hermes plugins install Shizoqua/hermes-scout/hermes_scout && hermes plugins enable hermes-scout
    ```

=== "pipx"

    ```bash
    pipx install hermes-scout
    ```

=== "pip"

    ```bash
    pip install hermes-scout
    ```

</div>

<p class="sc-meta">Zero dependencies &middot; Python 3.11 to 3.14 &middot; Linux, macOS, Windows &middot; MIT</p>

</div>

<section class="sc-section">
<p class="sc-kicker">Try it</p>
<h2 class="sc-title">Pick a question. See what comes back.</h2>
<p class="sc-sub">Real results from hermes-scout on a small sample project, recorded with
<code>nomic-embed-text</code> on Ollama.</p>

<div class="sc-play" data-playground>
  <div class="sc-chips" role="tablist">
    <button class="sc-chip" role="tab" data-q="0">how do we keep a copy of the database in case it gets lost</button>
    <button class="sc-chip" role="tab" data-q="1">E4021</button>
    <button class="sc-chip" role="tab" data-q="2">files like src/auth/tokens.py</button>
  </div>
  <div class="sc-term">
    <div class="sc-bar"><span></span><span></span><span></span><em>hermes-scout</em></div>
    <div class="sc-cmd"><span class="sc-prompt">$</span> <span data-cmd></span><span class="sc-caret"></span></div>
    <ol class="sc-results" data-results></ol>
    <p class="sc-note" data-note></p>
  </div>
  <label class="sc-compare" data-compare-wrap><input type="checkbox" data-compare> Compare with keyword search</label>
</div>
</section>

<section class="sc-section">
<p class="sc-kicker">Get started</p>
<h2 class="sc-title">First search in three steps</h2>

<div class="sc-steps">
  <div class="sc-step"><span class="sc-num">1</span><h3>Start an embeddings server</h3>
  <p>Ollama is the easiest, and it runs on your machine.</p><code>ollama pull nomic-embed-text</code></div>
  <div class="sc-step"><span class="sc-num">2</span><h3>Check the setup</h3>
  <p>It names the fix in plain words if anything is missing.</p><code>hermes-scout doctor</code></div>
  <div class="sc-step"><span class="sc-num">3</span><h3>Ask</h3>
  <p>The first search builds the index; later ones reuse it.</p><code>hermes-scout search "backup plan" ~/notes</code></div>
</div>
</section>

<section class="sc-section" markdown>
<p class="sc-kicker">Use it from</p>
<h2 class="sc-title">Where you already work</h2>

=== "Hermes chat"

    An example conversation:

    ```text
    You      Which of my notes in ~/notes covers the backup plan?

    Hermes   (searches ~/notes with scout_search)
             It is in docs/backups.md, lines 1-15: a nightly pg_dump at
             02:00 UTC, with files kept for 30 days.
    ```

=== "/scout command"

    ```text
    /scout doctor            check the server, the model and keyword search
    /scout status            list the indexed folders
    /scout index ~/notes     build or refresh an index now
    /scout clear ~/notes     forget a folder's index
    ```

=== "Terminal"

    ```bash
    hermes-scout search "how do we handle rate limits" ~/project
    hermes-scout search E4021 ~/project --ranking keyword
    hermes-scout similar notes/ideas.md --in ~/notes
    hermes-scout search "restore drill" ~/reports -g "*.pdf" --json
    ```

</section>

<section class="sc-section">
<p class="sc-kicker">Measured, not claimed</p>
<h2 class="sc-title">30 questions with known answers</h2>
<p class="sc-sub">Right file first, on a public benchmark that reruns on every change to the ranking code.</p>

<div class="sc-bars" data-bars>
  <div class="sc-bar-row"><span>hermes-scout, all questions</span><div><i style="--v:93%"></i></div><b>93%</b></div>
  <div class="sc-bar-row"><span>hermes-scout, reworded questions</span><div><i style="--v:89%"></i></div><b>89%</b></div>
  <div class="sc-bar-row sc-dim"><span>keyword search, reworded questions</span><div><i style="--v:39%"></i></div><b>39%</b></div>
</div>
<p class="sc-sub"><a href="benchmark/">Method and full results</a></p>
</section>

<section class="sc-section">
<p class="sc-kicker">Honest fit</p>
<h2 class="sc-title">Good for, and not for</h2>

<div class="sc-fit">
  <div class="sc-yes"><h3>Good for</h3><ul>
    <li>Finding a passage when you don't remember its words</li>
    <li>Code names and error codes, found exactly</li>
    <li>PDF, Word, Excel, PowerPoint and OpenDocument files, with the page, slide or sheet</li>
    <li>Private folders: indexing and search run on your machine</li>
  </ul></div>
  <div class="sc-no"><h3>Not for</h3><ul>
    <li>Searching the web</li>
    <li>Scanned PDFs, images and older .doc, .xls and .ppt files</li>
    <li>Chat memory or a document store</li>
    <li>Editing or uploading your files</li>
  </ul></div>
</div>
</section>

<section class="sc-section">
<p class="sc-kicker">Works with</p>
<h2 class="sc-title">Any OpenAI-compatible embeddings server</h2>
<div class="sc-logos">
  <a href="configuration/">Ollama</a><a href="configuration/">LM Studio</a><a href="configuration/">llama.cpp</a>
  <a href="configuration/">vLLM</a><a href="configuration/">Hosted APIs</a>
</div>
</section>

<div class="sc-cta">
  <h2>Ready when your files are.</h2>
  <p><a class="md-button md-button--primary" href="getting-started/">Get started</a>
  <a class="md-button" href="https://github.com/Shizoqua/hermes-scout">View on GitHub</a></p>
</div>
