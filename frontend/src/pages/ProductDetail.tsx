import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { formatPrice, getProduct, type ProductDetail as Detail } from '../api'

export default function ProductDetail() {
  const { productId = '' } = useParams()
  const [product, setProduct] = useState<Detail | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    setProduct(null)
    setError('')
    getProduct(productId)
      .then(setProduct)
      .catch(() => setError('Sorry, we could not find that product.'))
  }, [productId])

  return (
    <>
      <Link to="/products" className="back-link">
        ← Back to Products
      </Link>
      {error && <p className="error">{error}</p>}
      {!product && !error && <p className="muted">Loading…</p>}
      {product && (
        <div className="product-detail">
          <img src={product.image_url} alt={product.name} />
          <div className="product-info">
            <p className="garment-type">{product.garment_type}</p>
            <h1>{product.name}</h1>
            <p className="price">{formatPrice(product.price)}</p>
            <p>{product.description}</p>
            <p>
              <strong>Colors:</strong> {product.colors.join(', ')}
            </p>

            <h2>Sizes &amp; Stock</h2>
            <table className="stock-table">
              <thead>
                <tr>
                  <th>Size</th>
                  <th>In stock</th>
                </tr>
              </thead>
              <tbody>
                {product.inventory.map((s) => (
                  <tr key={s.size} className={s.quantity === 0 ? 'sold-out' : ''}>
                    <td>{s.size}</td>
                    <td>{s.quantity === 0 ? 'Sold out' : s.quantity}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="muted">Total in stock: {product.total_stock}</p>
          </div>
        </div>
      )}
    </>
  )
}
