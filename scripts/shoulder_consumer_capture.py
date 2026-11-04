"""Immutable fresh Stytch captures of the delivered #67 rig, not derived poses."""
REVISION = "a760e57a08d526088632b8cd269c391deeb3ecfb"
SOURCE_BASE = "godot/Stytch.GodotHost/Assets/Embodiment/Candidates/MeshVennDollShoulderAlignedV1/Evidence/Factory/"
ASSET_SHA = "6654f85acb539e471ccc525f4ffc029409e96e98aeb524df1be95211e860d3f8"
INDEX_SHA256 = "e2285869ae4e5237791ada40bc1b0cc6253d324c120aad1b97e1fb9b7d2ead32"
SOURCE_BLOBS = {
    "factory-hall.pose.json": "887b53fc6eaadfe35ce74c0cea4cc206b459632f",
    "factory-held.pose.json": "aaa25143d14647539cae163ff8f39be756c860d7",
    "factory-one-leg.pose.json": "3b27266b75b172f22e5b9888a018295831ff0406",
    "Walk/meshvenn-walk-00.pose.json": "646d695aac137eedc33b7bd3c45f20f437593b53",
    "Walk/meshvenn-walk-01.pose.json": "1cb447d12d8375b12b6c3f6401bf9730f74effee",
    "Walk/meshvenn-walk-02.pose.json": "e352b916680e6861a27db078edc49694473de117",
    "World/03-one-leg-hop.pose.json": "322931d2299061367825b6765e990f85b2f3603c",
    **{f"Hop/meshvenn-hop-{i:02}.pose.json": blob for i, blob in enumerate((
        "96cdd19b4ccc534ffeb1d2b4e5ab7e81d605312b", "c795d1d54ba2f512b70b47714e6891c291567537",
        "e6c43d70f69389163609c56d920338e6fbb29726", "19a09a808c32adb06ed6f769e4f4454e03136b72",
        "eb46b687848ddfea0a7292f4c8bd687478e982d2", "5f8f3126a8f995e4dcee33e0e9ddb2931ecd2456",
        "affcc545ae55896828b40fa32f0b3dc40891148e", "2d396bf1fbb7e8caae430e49bf2a86782899da83",
        "3074b8b1e821d2b4c188a7cdf2238b411b260357", "05835b4aa925b9a4976dfaf54e580d2c42c915a0",
        "a0fbe53db5abe1aeb690463af14fdca50ffdc02b", "477707be29cf8c5dcfb7c4c226b9bf3312b149a6"))},
}
