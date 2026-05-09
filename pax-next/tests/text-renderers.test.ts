/**
 * Tests for tekst-rendering-helpers i analyse-resultat.tsx.
 *
 * - splitKlagepunkt: deler en klagepunkt-streng i 'titel' (bold-vist)
 *   og 'rest' (brødtekst). Bruges i klagepunkt-listen i førstevurdering.
 * - parseAfgoerelse: parser rå afgørelses-tekst til strukturerede
 *   AfgBlok[] (overskrifter + afsnit), så uddraget kan vises i samme
 *   format som pakkerejseankenaevnet.dk.
 *
 * Ren funktionel logik — ingen eksterne dependencies, hurtige tests.
 */
import { describe, it, expect } from "vitest";

import {
  parseAfgoerelse,
  splitKlagepunkt,
} from "@/components/analyse-resultat";

// ─────────── splitKlagepunkt ───────────

describe("splitKlagepunkt", () => {
  it("splitter på kolon når det er inden for første 55 tegn", () => {
    const r = splitKlagepunkt("Manglende standard: hotellet var i ringe stand");
    expect(r.titel).toBe("Manglende standard");
    expect(r.rest).toBe("hotellet var i ringe stand");
  });

  it("splitter på tankestreg", () => {
    const r = splitKlagepunkt("Forsinkelse — fly afgik 6 timer for sent");
    expect(r.titel).toBe("Forsinkelse");
    expect(r.rest).toBe("fly afgik 6 timer for sent");
  });

  it("fjerner 'Klagepunkt N:' præfiks før split", () => {
    const r = splitKlagepunkt("Klagepunkt 1: Manglende standard, hotellet uacceptabelt");
    expect(r.titel).toBe("Manglende standard");
    expect(r.rest).toContain("hotellet uacceptabelt");
  });

  it("fjerner 'Punkt N.' præfiks", () => {
    const r = splitKlagepunkt("Punkt 2. Forsinkelse, fly forsinket");
    expect(r.titel).toBe("Forsinkelse");
  });

  it("fjerner 'Sekundært punkt a:' præfiks", () => {
    const r = splitKlagepunkt("Sekundært punkt a: Madkvalitet, ringe morgenmad");
    expect(r.titel).toBe("Madkvalitet");
  });

  it("falder tilbage til 4-ord-titel hvis ingen separator inden for 55 tegn", () => {
    const r = splitKlagepunkt(
      "Klager mente at hotellet ikke svarede til beskrivelsen i kataloget"
    );
    expect(r.titel.split(/\s+/).length).toBeLessThanOrEqual(4);
    expect(r.rest).toContain("til beskrivelsen");
  });

  it("returnerer hele teksten som titel hvis under 4 ord", () => {
    const r = splitKlagepunkt("Manglende standard hotel");
    expect(r.titel).toBe("Manglende standard hotel");
    expect(r.rest).toBe("");
  });

  it("trimmer whitespace", () => {
    const r = splitKlagepunkt("  Manglende standard:   hotel ringe   ");
    expect(r.titel).toBe("Manglende standard");
    expect(r.rest).toBe("hotel ringe");
  });
});

// ─────────── parseAfgoerelse ───────────

describe("parseAfgoerelse", () => {
  it("genkender kanoniske overskrifter som overskrift-blokke", () => {
    const tekst =
      "Klagens indhold\n\nKlager rejste til Mallorca i juli 2024.";
    const blokke = parseAfgoerelse(tekst);
    expect(blokke[0]).toEqual({
      type: "overskrift",
      tekst: "Klagens indhold",
    });
    expect(blokke[1].type).toBe("afsnit");
    expect(blokke[1].tekst).toContain("Mallorca");
  });

  it("strip kolon eller punktum fra overskrift", () => {
    const tekst = "Nævnets bemærkninger og afgørelse.\n\nNævnet finder...";
    const blokke = parseAfgoerelse(tekst);
    expect(blokke[0]).toEqual({
      type: "overskrift",
      tekst: "Nævnets bemærkninger og afgørelse",
    });
  });

  it("samler flere linjer i samme afsnit til én tekst-blok", () => {
    const tekst = "Linje 1\nLinje 2\nLinje 3";
    const blokke = parseAfgoerelse(tekst);
    expect(blokke).toHaveLength(1);
    expect(blokke[0].type).toBe("afsnit");
    expect(blokke[0].tekst).toBe("Linje 1 Linje 2 Linje 3");
  });

  it("splitter afsnit på blank linje", () => {
    const tekst = "Første afsnit.\n\nAndet afsnit.";
    const blokke = parseAfgoerelse(tekst);
    expect(blokke).toHaveLength(2);
    expect(blokke[0].tekst).toBe("Første afsnit.");
    expect(blokke[1].tekst).toBe("Andet afsnit.");
  });

  it("håndterer realistisk afgørelses-struktur", () => {
    const tekst = `Klagens indhold

Klager rejste til Mallorca i juli 2024 sammen med ægtefælle og to børn. Klager mener at hotellet ikke svarede til beskrivelsen.

Indklagedes bemærkninger

Indklagede afviser klagen og henviser til at hotellet svarede til kataloget.

Nævnets bemærkninger og afgørelse

Nævnet finder, at klagen ikke kan tages til følge.

Konklusion

Klagen tages ikke til følge.`;

    const blokke = parseAfgoerelse(tekst);
    const overskrifter = blokke
      .filter((b) => b.type === "overskrift")
      .map((b) => b.tekst);

    expect(overskrifter).toEqual([
      "Klagens indhold",
      "Indklagedes bemærkninger",
      "Nævnets bemærkninger og afgørelse",
      "Konklusion",
    ]);
    // 4 overskrifter + 4 afsnit
    expect(blokke).toHaveLength(8);
  });

  it("returnerer tom liste for tom input", () => {
    expect(parseAfgoerelse("")).toEqual([]);
    expect(parseAfgoerelse("   \n\n  ")).toEqual([]);
  });

  it("ignorerer non-overskrifter selv hvis de står på egen linje", () => {
    // Korte linjer der IKKE er kanoniske overskrifter skal være afsnit,
    // ikke overskrifter
    const tekst = "Et eller andet kort.\n\nEn anden ting.";
    const blokke = parseAfgoerelse(tekst);
    expect(blokke.every((b) => b.type === "afsnit")).toBe(true);
  });

  it("er case-insensitive på overskrift-matching", () => {
    const tekst = "klagens indhold\n\nKlager skrev...";
    const blokke = parseAfgoerelse(tekst);
    expect(blokke[0].type).toBe("overskrift");
  });
});
