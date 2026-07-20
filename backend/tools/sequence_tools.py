import re

CODON_TABLE = {
    'TTT': 'Phe', 'TTC': 'Phe',
    'TTA': 'Leu', 'TTG': 'Leu', 'CTT': 'Leu', 'CTC': 'Leu', 'CTA': 'Leu', 'CTG': 'Leu',
    'ATT': 'Ile', 'ATC': 'Ile', 'ATA': 'Ile',
    'ATG': 'Met',
    'GTT': 'Val', 'GTC': 'Val', 'GTA': 'Val', 'GTG': 'Val',
    'TCT': 'Ser', 'TCC': 'Ser', 'TCA': 'Ser', 'TCG': 'Ser', 'AGT': 'Ser', 'AGC': 'Ser',
    'CCT': 'Pro', 'CCC': 'Pro', 'CCA': 'Pro', 'CCG': 'Pro',
    'ACT': 'Thr', 'ACC': 'Thr', 'ACA': 'Thr', 'ACG': 'Thr',
    'GCT': 'Ala', 'GCC': 'Ala', 'GCA': 'Ala', 'GCG': 'Ala',
    'TAT': 'Tyr', 'TAC': 'Tyr',
    'TAA': 'Stop', 'TAG': 'Stop', 'TGA': 'Stop',
    'CAT': 'His', 'CAC': 'His',
    'CAA': 'Gln', 'CAG': 'Gln',
    'AAT': 'Asn', 'AAC': 'Asn',
    'AAA': 'Lys', 'AAG': 'Lys',
    'GAT': 'Asp', 'GAC': 'Asp',
    'GAA': 'Glu', 'GAG': 'Glu',
    'TGT': 'Cys', 'TGC': 'Cys',
    'TGG': 'Trp',
    'CGT': 'Arg', 'CGC': 'Arg', 'CGA': 'Arg', 'CGG': 'Arg', 'AGA': 'Arg', 'AGG': 'Arg',
    'GGT': 'Gly', 'GGC': 'Gly', 'GGA': 'Gly', 'GGG': 'Gly',
}

ONE_LETTER = {
    'Phe': 'F', 'Leu': 'L', 'Ile': 'I', 'Met': 'M', 'Val': 'V',
    'Ser': 'S', 'Pro': 'P', 'Thr': 'T', 'Ala': 'A', 'Tyr': 'Y',
    'Stop': '*', 'His': 'H', 'Gln': 'Q', 'Asn': 'N', 'Lys': 'K',
    'Asp': 'D', 'Glu': 'E', 'Cys': 'C', 'Trp': 'W', 'Arg': 'R', 'Gly': 'G',
}


def translate(dna: str) -> str:
    dna = dna.upper().replace('U', 'T')
    aas = []
    for i in range(0, len(dna) - 2, 3):
        codon = dna[i:i + 3]
        if len(codon) < 3:
            break
        aa = CODON_TABLE.get(codon, '?')
        if aa == 'Stop':
            break
        aas.append(ONE_LETTER.get(aa, aa))
    return ''.join(aas)


def find_orf(dna: str) -> str:
    dna = dna.upper().replace('U', 'T')
    start = dna.find('ATG')
    if start == -1:
        return ''
    orf_seq = dna[start:]
    codons = []
    for i in range(0, len(orf_seq) - 2, 3):
        codon = orf_seq[i:i + 3]
        if len(codon) < 3:
            break
        codons.append(codon)
        if CODON_TABLE.get(codon) == 'Stop':
            break
    return ''.join(codons)


def gc_content(dna: str) -> float:
    dna = dna.upper()
    if not dna:
        return 0.0
    return (dna.count('G') + dna.count('C')) / len(dna) * 100


def reverse_complement(dna: str) -> str:
    comp = {'A': 'T', 'T': 'A', 'G': 'C', 'C': 'G', 'N': 'N'}
    return ''.join(comp.get(b, b) for b in dna.upper())[::-1]


def is_valid_dna(seq: str) -> bool:
    return bool(seq) and all(c in 'ATGCatgcNn' for c in seq)


def detect_input_type(query: str) -> dict:
    """Classify query as rs_id, hgvs, gene_variant, or raw_dna."""
    query = query.strip()

    if re.match(r'^rs\d+$', query, re.I):
        return {'type': 'rs_id', 'rs_id': query.lower()}

    # HGVS with gene prefix: "BRCA1 c.5266dupC"
    m = re.match(r'^(\w[\w\-\.]+)\s+(c\..+)$', query, re.I)
    if m:
        return {'type': 'hgvs', 'gene': m.group(1).upper(), 'cdna': m.group(2)}

    # Bare HGVS
    if re.match(r'^c\.', query, re.I):
        return {'type': 'hgvs_bare', 'cdna': query}

    # Raw DNA
    if is_valid_dna(query) and len(query) >= 10:
        return {'type': 'raw_dna', 'sequence': query.upper()}

    # Fallback: treat as a gene name / search term
    return {'type': 'search', 'term': query}


def parse_hgvs_cdna(hgvs: str) -> dict:
    result = {'raw': hgvs, 'variant_type': 'unknown'}

    m = re.match(r'c\.(\d+)dup([ATGCatgc]+)', hgvs, re.I)
    if m:
        result.update({'variant_type': 'duplication', 'position': int(m.group(1)), 'sequence': m.group(2).upper()})
        return result

    m = re.match(r'c\.(\d+)ins([ATGCatgc]+)', hgvs, re.I)
    if m:
        result.update({'variant_type': 'insertion', 'position': int(m.group(1)), 'sequence': m.group(2).upper()})
        return result

    m = re.match(r'c\.(\d+)([ATGCatgc])>([ATGCatgc])', hgvs, re.I)
    if m:
        result.update({'variant_type': 'substitution', 'position': int(m.group(1)),
                       'ref': m.group(2).upper(), 'alt': m.group(3).upper()})
        return result

    m = re.match(r'c\.(\d+)del([ATGCatgc]*)', hgvs, re.I)
    if m:
        result.update({'variant_type': 'deletion', 'position': int(m.group(1)),
                       'sequence': m.group(2).upper() if m.group(2) else ''})
        return result

    return result
