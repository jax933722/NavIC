"use client";

import { useCallback, useEffect, useState } from "react";
import { addSeed, deleteSeed, listSeeds, type SeedTarget } from "@/lib/api";

// Sources that need a company website to anchor the leads they produce.
const JOB_BOARDS = new Set(["greenhouse", "lever", "ashby", "workable"]);

const EXAMPLES: Record<string, string> = {
  greenhouse: "https://boards-api.greenhouse.io/v1/boards/<token>/jobs",
  lever: "https://api.lever.co/v0/postings/<token>?mode=json",
  ashby: "https://api.ashbyhq.com/posting-api/job-board/<org>",
  workable: "https://<account>.workable.com/spi/v3/jobs",
  rss_blog: "https://example.com/blog/feed.xml",
  company_web: "https://example.com",
  hn_freelance: "(built-in — leave the default)",
  reddit_forhire: "https://www.reddit.com/r/forhire/new.json?limit=100",
};

export default function SourcesPage() {
  const [targets, setTargets] = useState<SeedTarget[]>([]);
  const [sources, setSources] = useState<string[]>([]);
  const [source, setSource] = useState("greenhouse");
  const [url, setUrl] = useState("");
  const [domain, setDomain] = useState("");
  const [name, setName] = useState("");
  const [err, setErr] = useState("");
  const [loaded, setLoaded] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const res = await listSeeds();
      setTargets(res.data);
      setSources(res.sources);
      setLoaded(true);
    } catch {
      setErr("Could not reach the API.");
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    setErr("");
    try {
      await addSeed({
        source,
        url,
        company_domain: domain || undefined,
        company_name: name || undefined,
      });
      setUrl("");
      setDomain("");
      setName("");
      refresh();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "failed");
    }
  }

  const input = { padding: "9px 12px" } as const;
  const needsDomain = JOB_BOARDS.has(source);

  return (
    <main className="container">
      <h1 className="h1">Sources</h1>
      <p className="sub">
        Choose exactly which company job boards and feeds the crawler pulls from. Add a
        target here, then press <b>Start crawling</b> on the Opportunities page. If you
        add nothing, the crawler falls back to the built-in community monitors (Hacker
        News freelancer threads, r/forhire).
      </p>

      <form onSubmit={add} className="card" style={{ marginBottom: 16 }}>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
          <select
            className="tierbtn"
            style={input}
            value={source}
            onChange={(e) => setSource(e.target.value)}
          >
            {(sources.length ? sources : [source]).map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          <input
            className="tierbtn"
            style={{ ...input, flex: "2 1 320px" }}
            placeholder={EXAMPLES[source] ?? "https://…"}
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            required
          />
          <input
            className="tierbtn"
            style={{ ...input, flex: "1 1 180px" }}
            placeholder={needsDomain ? "company website (required) — acme.com" : "company website (optional)"}
            value={domain}
            onChange={(e) => setDomain(e.target.value)}
            required={needsDomain}
          />
          <input
            className="tierbtn"
            style={{ ...input, flex: "1 1 150px" }}
            placeholder="company name (optional)"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <button className="tierbtn" type="submit" style={{ fontWeight: 600 }}>
            Add
          </button>
        </div>
        {needsDomain && (
          <p className="sub" style={{ margin: "8px 0 0" }}>
            Job boards return an applicant-tracking URL, not the company&rsquo;s own site — so
            add the <b>company website</b> to anchor the leads (you know it: it&rsquo;s why
            you&rsquo;re watching that board).
          </p>
        )}
        {err && (
          <p className="sub" style={{ color: "#e06c6c", margin: "8px 0 0" }}>
            {err}
          </p>
        )}
      </form>

      {loaded && targets.length === 0 && (
        <div className="empty">
          No targets yet — the crawler will use the built-in community monitors. Add a
          job board or feed above to watch specific companies.
        </div>
      )}

      {targets.map((t) => (
        <div key={t.id} className="card" style={{ display: "flex", alignItems: "center",
          gap: 12, justifyContent: "space-between" }}>
          <div>
            <b>{t.source}</b>
            {t.company_domain ? (
              <span className="mono"> · {t.company_name ?? t.company_domain} ({t.company_domain})</span>
            ) : null}
            <div className="mono" style={{ fontSize: 12, opacity: 0.75, marginTop: 2 }}>
              {t.url}
            </div>
          </div>
          <button
            className="tierbtn"
            style={{ color: "#e06c6c", borderColor: "#e06c6c" }}
            onClick={async () => {
              await deleteSeed(t.id);
              refresh();
            }}
          >
            Remove
          </button>
        </div>
      ))}
    </main>
  );
}
