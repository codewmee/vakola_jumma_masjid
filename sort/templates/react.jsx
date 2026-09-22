import { motion } from "framer-motion";
import { useState } from "react";

export default function LiquidBallsUI() {
  const [active, setActive] = useState(null);

  const handleClick = (id) => {
    if (active) return;
    setActive(id);
  };

  const Ball = ({ id, left, img, title }) => {
    const isActive = active === id;
    const isOtherHidden = active && active !== id;

    return (
      <motion.div
        initial={{ y: -100, scaleY: 0.8, scaleX: 1.2 }}
        animate={{
          y: active ? 0 : 400,
          scale: isActive ? 8 : isOtherHidden ? 0.5 : 1,
          opacity: isOtherHidden ? 0 : 1,
        }}
        transition={{
          type: "spring",
          stiffness: 120,
          damping: 10,
        }}
        onClick={() => handleClick(id)}
        className="absolute cursor-pointer flex items-center justify-center overflow-hidden rounded-full bg-black"
        style={{
          width: "130px",
          height: "130px",
          left: left,
          top: "16px",
          zIndex: isActive ? 20 : 5,
          border: "2px solid transparent",
        }}
        whileHover={{
          scale: 1.08,
          boxShadow: "0 0 25px rgba(255,255,0,0.5)",
          border: "2px solid yellow",
        }}
      >
        {/* IMAGE */}
        <motion.img
          src={img}
          alt=""
          className="w-full h-full object-cover"
          initial={{ opacity: 0 }}
          whileHover={{ opacity: 1 }}
          transition={{ duration: 0.3 }}
        />
      </motion.div>
    );
  };

  return (
    <div className={`h-screen w-full ${active ? "bg-black" : "bg-white"} transition-all duration-500`}>

      {/* NAVBAR */}
      <div className="w-full h-16 bg-black text-white flex items-center justify-center fixed top-0">
        <h1 className="tracking-widest">My UI</h1>
      </div>

      {/* BALLS */}
      <Ball
        id="one"
        left="35%"
        img="https://source.unsplash.com/300x300/?nature"
        title="Nature"
      />

      <Ball
        id="two"
        left="55%"
        img="https://source.unsplash.com/300x300/?technology"
        title="Tech"
      />

      {/* CONTENT */}
      {active === "one" && (
        <div className="absolute text-white text-center top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-30">
          <h1 className="text-4xl font-bold mb-4">Nature 🌿</h1>
          <p>Data for Ball 1</p>
        </div>
      )}

      {active === "two" && (
        <div className="absolute text-white text-center top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-30">
          <h1 className="text-4xl font-bold mb-4">Technology 💻</h1>
          <p>Data for Ball 2</p>
        </div>
      )}
    </div>
  );
}