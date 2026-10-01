import { useLayoutEffect, useRef, type ImgHTMLAttributes } from "react";

type Props = Omit<ImgHTMLAttributes<HTMLImageElement>, "src"> & {
  src: string;
};

export default function ManagedStreamImage({ src, ...imageProps }: Props) {
  const imageRef = useRef<HTMLImageElement | null>(null);

  useLayoutEffect(() => {
    const image = imageRef.current;
    if (!image) return;
    image.src = src;
    return () => {
      image.removeAttribute("src");
    };
  }, [src]);

  return <img {...imageProps} ref={imageRef} />;
}
