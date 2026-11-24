# ruff: noqa: E501
"""Bounded original STEM templates (distinct semantics, not index clones)."""

from __future__ import annotations

# Each entry: (stem_without_prefix, options_dict, correct_key, topic_code)
# Prefix added by builder.

IMAT_BIOLOGY_BANK: tuple[tuple[str, dict[str, str], str, str], ...] = (
    (
        "Which organelle performs cellular respiration?",
        {"A": "mitochondrion", "B": "nucleus", "C": "ribosome", "D": "golgi", "E": "lysosome"},
        "A",
        "biology_cell",
    ),
    (
        "Which organelle conducts photosynthesis?",
        {"A": "chloroplast", "B": "mitochondrion", "C": "vacuole", "D": "centriole", "E": "nucleolus"},
        "A",
        "biology_cell",
    ),
    (
        "Where is DNA primarily stored in eukaryotic cells?",
        {"A": "nucleus", "B": "cytoplasm", "C": "cell wall", "D": "plasma membrane", "E": "cytosol"},
        "A",
        "biology_cell",
    ),
    (
        "Which blood component carries oxygen?",
        {"A": "erythrocytes", "B": "platelets", "C": "plasma proteins", "D": "lymphocytes", "E": "neutrophils"},
        "A",
        "biology_human",
    ),
    (
        "Insulin is secreted by which pancreatic cells?",
        {"A": "beta cells", "B": "alpha cells", "C": "delta cells", "D": "acinar cells", "E": "goblet cells"},
        "A",
        "biology_human",
    ),
    (
        "Which molecule stores genetic information?",
        {"A": "DNA", "B": "ATP", "C": "glucose", "D": "urea", "E": "lactic acid"},
        "A",
        "biology_cell",
    ),
    (
        "Which process builds proteins from mRNA?",
        {"A": "translation", "B": "transcription", "C": "replication", "D": "fermentation", "E": "glycolysis"},
        "A",
        "biology_cell",
    ),
    (
        "Mendel studied inheritance using which organism?",
        {"A": "pea plants", "B": "fruit flies", "C": "E. coli", "D": "yeast", "E": "corn only"},
        "A",
        "biology_genetics",
    ),
    (
        "Which gas do plants absorb for photosynthesis?",
        {"A": "carbon dioxide", "B": "nitrogen", "C": "argon", "D": "hydrogen", "E": "helium"},
        "A",
        "biology_cell",
    ),
    (
        "Which structure controls what enters the cell?",
        {"A": "plasma membrane", "B": "ribosome", "C": "nucleolus", "D": "centriole", "E": "chromoplast"},
        "A",
        "biology_cell",
    ),
)

IMAT_CHEMISTRY_BANK: tuple[tuple[str, dict[str, str], str, str], ...] = (
    (
        "What is the formula of water?",
        {"A": "H2O", "B": "CO2", "C": "NaCl", "D": "O2", "E": "CH4"},
        "A",
        "chemistry",
    ),
    (
        "Which element has atomic number 6?",
        {"A": "carbon", "B": "nitrogen", "C": "oxygen", "D": "sodium", "E": "iron"},
        "A",
        "chemistry",
    ),
    (
        "Table salt is primarily which compound?",
        {"A": "NaCl", "B": "H2O", "C": "CaCO3", "D": "MgO", "E": "KNO3"},
        "A",
        "chemistry",
    ),
    (
        "Which particle has positive charge in the nucleus?",
        {"A": "proton", "B": "electron", "C": "neutron", "D": "positron", "E": "photon"},
        "A",
        "chemistry",
    ),
    (
        "Burning hydrocarbons produces chiefly?",
        {"A": "CO2 and H2O", "B": "O2 only", "C": "N2 only", "D": "NaCl", "E": "He"},
        "A",
        "chemistry",
    ),
    (
        "pH 7 at 25C indicates?",
        {"A": "neutral solution", "B": "strong acid", "C": "strong base", "D": "salt only", "E": "plasma"},
        "A",
        "chemistry",
    ),
    (
        "Avogadro's number relates moles to?",
        {"A": "particles", "B": "volume only", "C": "mass only", "D": "temperature", "E": "pressure"},
        "A",
        "chemistry",
    ),
    (
        "Which bond shares electron pairs?",
        {"A": "covalent", "B": "ionic only", "C": "metallic only", "D": "van der Waals", "E": "gravity"},
        "A",
        "chemistry",
    ),
    (
        "Rust involves oxidation of?",
        {"A": "iron", "B": "gold", "C": "platinum", "D": "silver only", "E": "helium"},
        "A",
        "chemistry",
    ),
    (
        "Which gas is diatomic in standard state?",
        {"A": "oxygen", "B": "neon", "C": "argon", "D": "helium", "E": "xenon only"},
        "A",
        "chemistry",
    ),
)

IMAT_PHYSICS_BANK: tuple[tuple[str, dict[str, str], str, str], ...] = (
    (
        "SI unit of force?",
        {"A": "newton", "B": "joule", "C": "watt", "D": "pascal", "E": "ampere"},
        "A",
        "physics",
    ),
    (
        "SI unit of electric current?",
        {"A": "ampere", "B": "volt", "C": "ohm", "D": "coulomb", "E": "tesla"},
        "A",
        "physics",
    ),
    (
        "Speed is distance divided by?",
        {"A": "time", "B": "mass", "C": "force", "D": "area", "E": "charge"},
        "A",
        "physics",
    ),
    (
        "Kinetic energy depends on mass and?",
        {"A": "velocity squared", "B": "charge", "C": "pressure", "D": "resistance", "E": "volume"},
        "A",
        "physics",
    ),
    (
        "Light travels fastest in?",
        {"A": "vacuum", "B": "water", "C": "glass", "D": "diamond", "E": "steel"},
        "A",
        "physics",
    ),
    (
        "Gravitational acceleration near Earth is about?",
        {"A": "9.8 m/s^2", "B": "1 m/s^2", "C": "98 m/s", "D": "0.98 m/s^2", "E": "980 m/s^2"},
        "A",
        "physics",
    ),
    (
        "Ohm's law relates voltage, current, and what quantity?",
        {"A": "resistance", "B": "mass", "C": "pressure", "D": "entropy", "E": "luminance"},
        "A",
        "physics",
    ),
    (
        "Frequency unit is?",
        {"A": "hertz", "B": "newton", "C": "joule", "D": "pascal", "E": "watt"},
        "A",
        "physics",
    ),
    (
        "Which wave needs a medium?",
        {"A": "sound", "B": "light in vacuum", "C": "gamma rays", "D": "X-rays in vacuum", "E": "radio in vacuum"},
        "A",
        "physics",
    ),
    (
        "Momentum is mass times?",
        {"A": "velocity", "B": "acceleration", "C": "force", "D": "energy", "E": "pressure"},
        "A",
        "physics",
    ),
)

CA_ECONOMICS_TOPICS: tuple[tuple[str, dict[str, str], str], ...] = (
    (
        "Opportunity cost is best defined as:",
        {
            "A": "Accounting profit after tax",
            "B": "Value of the next best alternative forgone",
            "C": "Total revenue minus explicit costs",
            "D": "Marginal cost of production",
        },
        "B",
    ),
    (
        "Law of demand states that when price rises, quantity demanded:",
        {"A": "Rises", "B": "Falls", "C": "Unchanged", "D": "Doubles"},
        "B",
    ),
    (
        "GDP measures the total value of:",
        {"A": "final goods and services", "B": "intermediate goods only", "C": "exports only", "D": "imports only"},
        "A",
    ),
    (
        "Inflation is a sustained rise in:",
        {"A": "general price level", "B": "employment only", "C": "exports", "D": "tax revenue"},
        "A",
    ),
    (
        "A monopoly has how many sellers in the market?",
        {"A": "one", "B": "two", "C": "many", "D": "infinite"},
        "A",
    ),
    (
        "Elastic demand means quantity responds:",
        {"A": "strongly to price changes", "B": "not at all", "C": "only to taxes", "D": "only to subsidies"},
        "A",
    ),
    (
        "Fiscal policy uses:",
        {"A": "government spending and taxation", "B": "money supply only", "C": "exchange rates only", "D": "patents"},
        "A",
    ),
    (
        "Comparative advantage explains gains from:",
        {"A": "trade specialization", "B": "tariffs only", "C": "price ceilings", "D": "black markets"},
        "A",
    ),
    (
        "Marginal cost is cost of producing:",
        {"A": "one additional unit", "B": "all units", "C": "fixed assets", "D": "past output"},
        "A",
    ),
    (
        "A budget deficit means government:",
        {"A": "spends more than revenue", "B": "saves more", "C": "exports exceed imports", "D": "taxes fall to zero"},
        "A",
    ),
)