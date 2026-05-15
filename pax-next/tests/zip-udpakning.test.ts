/**
 * Tests for lib/zip-udpakning.ts.
 *
 * Klient-side ZIP-udpakning så hver fil i en uploadet ZIP fremstår
 * individuelt i UI'et (Sagsakter-sektion, Anonymisér-sektion osv.) —
 * præcis som hvis brugeren havde uploadet filerne enkeltvis.
 *
 * Vi bruger ægte jszip — ingen mocks. Tests bygger små zip-buffers
 * in-memory og kører dem gennem `udpak_zips_klient`.
 */
import { describe, it, expect } from "vitest";
import JSZip from "jszip";

import { udpak_zips_klient } from "@/lib/zip-udpakning";

async function lavZipFile(
  navn: string,
  filer: Record<string, string | Uint8Array>,
): Promise<File> {
  const zip = new JSZip();
  for (const [n, indhold] of Object.entries(filer)) {
    zip.file(n, indhold);
  }
  const blob = await zip.generateAsync({ type: "blob" });
  return new File([blob], navn, { type: "application/zip" });
}

function tekstFile(navn: string, indhold: string): File {
  return new File([indhold], navn, { type: "text/plain" });
}

describe("udpak_zips_klient", () => {
  it("returnerer ikke-zip-filer uændret", async () => {
    const a = tekstFile("klage.pdf", "fake-pdf-bytes");
    const b = tekstFile("bilag.docx", "fake-docx-bytes");
    const res = await udpak_zips_klient([a, b]);
    expect(res.filer).toHaveLength(2);
    expect(res.filer.map((f) => f.name)).toEqual(["klage.pdf", "bilag.docx"]);
    expect(res.skipped_media).toEqual([]);
    expect(res.fejl).toEqual([]);
  });

  it("pakker en zip ud og fanout'er filerne", async () => {
    const zip = await lavZipFile("sag.zip", {
      "1. høring R.pdf": "pdf-bytes-1",
      "Bilag 01 Klageskema.pdf": "pdf-bytes-2",
      "Bilag 02.docx": "docx-bytes",
    });
    const res = await udpak_zips_klient([zip]);
    expect(res.filer.map((f) => f.name).sort()).toEqual([
      "1. høring R.pdf",
      "Bilag 01 Klageskema.pdf",
      "Bilag 02.docx",
    ]);
    expect(res.skipped_media).toEqual([]);
  });

  it("springer __MACOSX og skjulte filer over", async () => {
    const zip = await lavZipFile("sag.zip", {
      "klage.pdf": "ok",
      "__MACOSX/._klage.pdf": "macos-skrald",
      ".DS_Store": "skjult",
      "mappe/.skjult.pdf": "også skjult",
      "mappe/synlig.pdf": "synlig",
    });
    const res = await udpak_zips_klient([zip]);
    const navne = res.filer.map((f) => f.name).sort();
    expect(navne).toContain("klage.pdf");
    expect(navne).toContain("synlig.pdf");
    expect(navne).not.toContain("._klage.pdf");
    expect(navne).not.toContain(".DS_Store");
    expect(navne).not.toContain(".skjult.pdf");
  });

  it("springer mp4/video/lyd over og rapporterer dem", async () => {
    const zip = await lavZipFile("sag.zip", {
      "bilag.pdf": "ok",
      "video.mp4": "video-bytes",
      "lyd.mp3": "lyd-bytes",
      "movie.mov": "mov-bytes",
      "audio.m4a": "m4a-bytes",
    });
    const res = await udpak_zips_klient([zip]);
    expect(res.filer.map((f) => f.name)).toEqual(["bilag.pdf"]);
    expect(res.skipped_media.sort()).toEqual([
      "audio.m4a",
      "lyd.mp3",
      "movie.mov",
      "video.mp4",
    ]);
  });

  it("flader sti-prefiks (mappe/) til kort filnavn", async () => {
    const zip = await lavZipFile("sag.zip", {
      "bilag/01_klage.pdf": "ok",
      "bilag/sub/02_bilag.pdf": "også ok",
    });
    const res = await udpak_zips_klient([zip]);
    expect(res.filer.map((f) => f.name).sort()).toEqual([
      "01_klage.pdf",
      "02_bilag.pdf",
    ]);
  });

  it("bevarer fil-bytes så de kan re-uploades", async () => {
    const zip = await lavZipFile("sag.zip", {
      "klage.pdf": "hello world",
    });
    const res = await udpak_zips_klient([zip]);
    expect(res.filer).toHaveLength(1);
    const tekst = await res.filer[0].text();
    expect(tekst).toBe("hello world");
  });

  it("kan håndtere mix af zip og regulære filer", async () => {
    const zip = await lavZipFile("pakke.zip", {
      "bilag1.pdf": "ok",
      "bilag2.pdf": "ok",
    });
    const direkte = tekstFile("klage.pdf", "klage");
    const res = await udpak_zips_klient([direkte, zip]);
    expect(res.filer.map((f) => f.name).sort()).toEqual([
      "bilag1.pdf",
      "bilag2.pdf",
      "klage.pdf",
    ]);
  });

  it("returnerer fejl for ødelagt zip", async () => {
    const corrupt = new File(
      [new Uint8Array([1, 2, 3, 4, 5])],
      "ødelagt.zip",
      { type: "application/zip" },
    );
    const res = await udpak_zips_klient([corrupt]);
    expect(res.fejl).toHaveLength(1);
    expect(res.fejl[0].filnavn).toBe("ødelagt.zip");
    expect(res.fejl[0].besked).toMatch(/zip/i);
  });

  it("dropper mapper i zippen", async () => {
    // jszip laver tomme directory-entries når man bruger 'mappe/' prefix.
    // Vi skal IKKE oprette en tom File for selve mappen.
    const zip = await lavZipFile("sag.zip", {
      "mappe/fil.pdf": "ok",
    });
    const res = await udpak_zips_klient([zip]);
    expect(res.filer).toHaveLength(1);
    expect(res.filer[0].name).toBe("fil.pdf");
  });
});
