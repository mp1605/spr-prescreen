import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ExternalLink, Search } from "lucide-react";
import { get, type Registry } from "../api/client";
import { AdminAccess } from "../components/AdminAccess";
import { QueryState } from "../components/QueryState";
import {
  HeaderRefresh,
  PageHeaderActions,
} from "../components/PageHeaderActions";

export function Rules() {
  const [search, setSearch] = useState("");
  const [list, setList] = useState("all");
  const query = useQuery({
    queryKey: ["rules"],
    queryFn: () => get<Registry>("/api/rules"),
  });
  const items = useMemo(() => {
    const data = query.data;
    if (!data) return [];
    const all =
      list === "list1"
        ? data.list1
        : list === "list2"
          ? data.list2
          : [...data.list1, ...data.list2];
    const term = search.toLocaleLowerCase().trim();
    return all.filter((item) =>
      `${item.id} ${item.text} ${item.category ?? ""} ${item.examples ?? ""}`
        .toLocaleLowerCase()
        .includes(term),
    );
  }, [query.data, list, search]);
  if (!query.data)
    return (
      <QueryState error={query.error} retry={() => void query.refetch()} />
    );
  return (
    <>
      <PageHeaderActions>
        <a
          className="outline-button"
          href="/api/rules/source"
          target="_blank"
          rel="noreferrer"
        >
          Original guide <ExternalLink size={15} />
        </a>
        <a className="outline-button" href="#rule-management">
          Manage indicators
        </a>
        <HeaderRefresh
          label="Refresh official rules"
          busy={query.isFetching}
          refresh={() => void query.refetch()}
        />
      </PageHeaderActions>
      <div className="notice">
        <p className="policy-version">
          Read-only policy reference · {query.data.policy_version}
        </p>
        List 1 runs first. List 2 always follows, including when List 1
        identifies a flag. The guide has no List 1 item 2.
      </div>
      <div className="filters">
        <label className="search">
          <Search size={18} />
          <span className="sr-only">Search policy wording</span>
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search items, categories, or examples…"
          />
        </label>
        <label>
          <span className="sr-only">Filter by list</span>
          <select value={list} onChange={(e) => setList(e.target.value)}>
            <option value="all">Both lists</option>
            <option value="list1">List 1 · 8 items</option>
            <option value="list2">List 2 · 31 items</option>
          </select>
        </label>
        <span className="subtle" role="status">
          {items.length} {items.length === 1 ? "item" : "items"}
        </span>
      </div>
      <div className="rules-list">
        {items.map((item) => (
          <article className="rule-card" key={item.id}>
            <div className="rule-meta">
              <span className="rule-id">{item.id}</span>
              <span>Guide p. {item.source_pages.join(", ")}</span>
            </div>
            <div>
              {item.category && <h2>{item.category}</h2>}
              <p className="rule-wording">{item.text}</p>
              {item.examples && (
                <details>
                  <summary>Official examples</summary>
                  <p>{item.examples}</p>
                </details>
              )}
              <details>
                <summary>
                  Screening indicators ({item.detectors.length})
                </summary>
                <ul className="plain-list">
                  {item.detectors.map((detector) => (
                    <li key={detector.name}>{detector.name}</li>
                  ))}
                </ul>
              </details>
            </div>
          </article>
        ))}
        {items.length === 0 && (
          <div className="panel">
            <h2>No matching policy items</h2>
            <p>Try another phrase or select both lists.</p>
            <button
              onClick={() => {
                setSearch("");
                setList("all");
              }}
            >
              Reset filters
            </button>
          </div>
        )}
      </div>
      <AdminAccess />
      <div className="source-note">
        Source SHA-256 <code>{query.data.source_sha256}</code>
        <p>
          Wording and numbering follow the supplied guide. Current indicators
          work alongside semantic retrieval from the official wording.
          Thresholds are uncalibrated; source-bound specificity supports List 2
          colors.
        </p>
      </div>
    </>
  );
}
