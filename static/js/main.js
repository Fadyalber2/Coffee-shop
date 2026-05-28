// Cart functionality
document.addEventListener('DOMContentLoaded', function() {
    // Add to cart functionality
    const addToCartButtons = document.querySelectorAll('.add-to-cart');
    addToCartButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            e.preventDefault();
            const productId = this.dataset.productId;
            fetch('/add_to_cart/' + productId, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                }
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    // Update cart count
                    const cartCount = document.querySelector('.cart-count');
                    if (cartCount) {
                        cartCount.textContent = data.cart_count;
                    }
                    // Show success message
                    alert('Item added to cart!');
                } else {
                    alert('Please login to add items to cart');
                }
            })
            .catch(error => {
                console.error('Error:', error);
                alert('Error adding item to cart');
            });
        });
    });

    // Quantity control in cart
    const quantityInputs = document.querySelectorAll('.quantity-input');
    quantityInputs.forEach(input => {
        input.addEventListener('change', function() {
            const productId = this.dataset.productId;
            const quantity = this.value;
            
            fetch('/update_cart/' + productId, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    quantity: quantity
                })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    // Update total price
                    const totalElement = document.querySelector('.cart-total');
                    if (totalElement) {
                        totalElement.textContent = '$' + data.total.toFixed(2);
                    }
                    // Update item subtotal
                    const subtotalElement = document.querySelector('.subtotal-' + productId);
                    if (subtotalElement) {
                        subtotalElement.textContent = '$' + data.item_total.toFixed(2);
                    }
                } else {
                    alert('Error updating cart');
                }
            })
            .catch(error => {
                console.error('Error:', error);
                alert('Error updating cart');
            });
        });
    });

    // Remove from cart
    const removeButtons = document.querySelectorAll('.remove-from-cart');
    removeButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            e.preventDefault();
            const productId = this.dataset.productId;
            
            fetch('/remove_from_cart/' + productId, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                }
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    // Remove item element
                    const itemElement = document.querySelector('.cart-item-' + productId);
                    if (itemElement) {
                        itemElement.remove();
                    }
                    // Update total price
                    const totalElement = document.querySelector('.cart-total');
                    if (totalElement) {
                        totalElement.textContent = '$' + data.total.toFixed(2);
                    }
                    // Update cart count
                    const cartCount = document.querySelector('.cart-count');
                    if (cartCount) {
                        cartCount.textContent = data.cart_count;
                    }
                    // If cart is empty, refresh page to show empty cart message
                    if (data.cart_count === 0) {
                        location.reload();
                    }
                } else {
                    alert('Error removing item from cart');
                }
            })
            .catch(error => {
                console.error('Error:', error);
                alert('Error removing item from cart');
            });
        });
    });
});
