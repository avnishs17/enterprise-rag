import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SourcesPanel } from "./SourcesPanel";

describe("SourcesPanel", () => {
  it("renders citation labels, source names, and chunk content", () => {
    render(<SourcesPanel sources={["[S1] SOURCE: kubernetes.md\nCONTENT: A Pod runs one or more containers."]} />);

    expect(screen.getByText("Sources (1 chunks)")).toBeInTheDocument();
    expect(screen.getByText("[S1] kubernetes.md")).toBeInTheDocument();
    expect(screen.getByText("A Pod runs one or more containers.")).toBeInTheDocument();
  });

  it("renders legacy unlabeled chunks safely", () => {
    render(<SourcesPanel sources={["legacy chunk"]} />);

    expect(screen.getByText("[S1] Retrieved chunk 1")).toBeInTheDocument();
    expect(screen.getByText("legacy chunk")).toBeInTheDocument();
  });
});
