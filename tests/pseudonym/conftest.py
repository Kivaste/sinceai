def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "kit: needs the challenge kit (PETS_KIT or the pinned path); skipped if absent",
    )
