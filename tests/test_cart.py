def test_add_to_cart(client, first_product_id):
    response = client.post(f"/cart/add/{first_product_id}", follow_redirects=True)
    assert response.status_code == 200
    assert b"First Product" in client.get("/cart").data


def test_update_cart_quantity(client, first_product_id):
    client.post(f"/cart/add/{first_product_id}")
    client.post(f"/cart/update/{first_product_id}", data={"quantity": "3"})
    response = client.get("/cart")
    assert b'value="3"' in response.data
    assert b"$300.00" in response.data


def test_remove_from_cart(client, first_product_id):
    client.post(f"/cart/add/{first_product_id}")
    client.post(f"/cart/remove/{first_product_id}")
    assert b"Your cart is empty" in client.get("/cart").data
