import { Link, Route, Routes } from 'react-router-dom'
import NavBar from './NavBar'
import ChatWidget from './ChatWidget'
import { useCart } from './cart'
import { PeekingBulldog } from './Mascots'
import { Awning, StoreBackdrop } from './Storefront'
import Home from './pages/Home'
import Products from './pages/Products'
import ProductDetail from './pages/ProductDetail'
import AboutUs from './pages/AboutUs'
import LogIn from './pages/LogIn'
import CreateAccount from './pages/CreateAccount'
import Cart from './pages/Cart'

export default function App() {
  const { notice } = useCart()

  return (
    <>
      <StoreBackdrop />
      <NavBar />
      <Awning />
      <main className="page">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/products" element={<Products />} />
          <Route path="/products/:productId" element={<ProductDetail />} />
          <Route path="/about" element={<AboutUs />} />
          <Route path="/login" element={<LogIn />} />
          <Route path="/create-account" element={<CreateAccount />} />
          <Route path="/cart" element={<Cart />} />
        </Routes>
      </main>
      {notice?.kind === 'added' && (
        <div className="toast" role="status">
          <img src={notice.image_url} alt="" />
          <span>
            Added <strong>{notice.name}</strong> (size {notice.size}) to your cart
          </span>
          <Link to="/cart">View cart</Link>
        </div>
      )}
      {notice?.kind === 'error' && (
        <div className="toast toast-error" role="alert">
          <span>{notice.message}</span>
        </div>
      )}
      <PeekingBulldog />
      <ChatWidget />
    </>
  )
}
