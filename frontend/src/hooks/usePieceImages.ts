'use client';

import { useEffect, useState } from 'react';

interface ContentBounds {
  left: number;
  top: number;
  width: number;
  height: number;
}

export interface PieceImageData {
  img: HTMLImageElement;
  bounds: ContentBounds;
}

export type PieceImages = Record<string, PieceImageData>;

const IMAGE_KEYS = ['1-a', '1-b', '2-a', '2-b'] as const;

/**
 * Scan image pixels to find the bounding rectangle of non-white content.
 * Uses a threshold (channel < 240) to handle JPEG compression artifacts.
 */
function detectContentBounds(img: HTMLImageElement): ContentBounds {
  const canvas = document.createElement('canvas');
  canvas.width = img.naturalWidth;
  canvas.height = img.naturalHeight;
  const ctx = canvas.getContext('2d')!;
  ctx.drawImage(img, 0, 0);
  const data = ctx.getImageData(0, 0, canvas.width, canvas.height).data;

  let minX = canvas.width, maxX = 0, minY = canvas.height, maxY = 0;

  for (let y = 0; y < canvas.height; y++) {
    for (let x = 0; x < canvas.width; x++) {
      const i = (y * canvas.width + x) * 4;
      if (data[i] < 240 || data[i + 1] < 240 || data[i + 2] < 240) {
        if (x < minX) minX = x;
        if (x > maxX) maxX = x;
        if (y < minY) minY = y;
        if (y > maxY) maxY = y;
      }
    }
  }

  // Small padding to avoid clipping edge pixels
  const pad = 1;
  minX = Math.max(0, minX - pad);
  minY = Math.max(0, minY - pad);
  maxX = Math.min(canvas.width - 1, maxX + pad);
  maxY = Math.min(canvas.height - 1, maxY + pad);

  return { left: minX, top: minY, width: maxX - minX + 1, height: maxY - minY + 1 };
}

/**
 * Load the 4 piece images and detect their content bounds.
 * Returns null while loading, then a map keyed by "1-a", "1-b", "2-a", "2-b".
 */
export function usePieceImages(): PieceImages | null {
  const [images, setImages] = useState<PieceImages | null>(null);

  useEffect(() => {
    let cancelled = false;

    Promise.all(
      IMAGE_KEYS.map(
        key =>
          new Promise<[string, PieceImageData]>((resolve, reject) => {
            const img = new Image();
            img.onload = () => {
              const bounds = detectContentBounds(img);
              resolve([key, { img, bounds }]);
            };
            img.onerror = reject;
            img.src = `/assets/pieces/piece-player-${key}.jpg`;
          }),
      ),
    )
      .then(results => {
        if (cancelled) return;
        const map: PieceImages = {};
        for (const [key, data] of results) map[key] = data;
        setImages(map);
      })
      .catch(err => {
        console.warn('Failed to load piece images:', err);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return images;
}
