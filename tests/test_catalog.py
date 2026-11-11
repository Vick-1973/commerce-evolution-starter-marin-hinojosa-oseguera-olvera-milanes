def test_catalog_loads(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"First Product" in response.data
    assert b"Second Product" in response.data


def test_product_detail_loads(client, first_product_id):
    response = client.get(f"/products/{first_product_id}")
    assert response.status_code == 200
    assert b"First Product" in response.data


def test_missing_product_returns_404(client):
    assert client.get("/products/9999").status_code == 404
