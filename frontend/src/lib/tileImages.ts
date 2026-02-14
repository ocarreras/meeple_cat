/**
 * Tile image preloader for Carcassonne
 * Loads all 24 tile images (A-X) from /tiles/tile_A.png etc.
 */

const TILE_TYPES = [
  'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H',
  'I', 'J', 'K', 'L', 'M', 'N', 'O', 'P',
  'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X',
] as const;

export type TileType = typeof TILE_TYPES[number];

let imageCache: Map<string, HTMLImageElement> | null = null;
let loadingPromise: Promise<Map<string, HTMLImageElement>> | null = null;

/**
 * Preload all tile images
 * Returns a cached Map of tile type -> HTMLImageElement
 * Subsequent calls return the cached result immediately
 */
export async function preloadTileImages(): Promise<Map<string, HTMLImageElement>> {
  // Return cached result if available
  if (imageCache) {
    return imageCache;
  }

  // Return in-progress loading promise if available
  if (loadingPromise) {
    return loadingPromise;
  }

  // Start loading
  loadingPromise = new Promise((resolve, reject) => {
    const images = new Map<string, HTMLImageElement>();
    const loadPromises: Promise<void>[] = [];

    for (const tileType of TILE_TYPES) {
      const promise = new Promise<void>((resolveImage, rejectImage) => {
        const img = new Image();
        const src = `/tiles/tile_${tileType}.svg`;

        img.onload = () => {
          images.set(tileType, img);
          resolveImage();
        };

        img.onerror = () => {
          console.error(`Failed to load tile image: ${src}`);
          rejectImage(new Error(`Failed to load tile image: ${src}`));
        };

        img.src = src;
      });

      loadPromises.push(promise);
    }

    Promise.all(loadPromises)
      .then(() => {
        imageCache = images;
        resolve(images);
      })
      .catch(reject);
  });

  return loadingPromise;
}

/**
 * Get a single tile image
 * Returns the cached image if available, otherwise returns null
 */
export function getTileImage(tileType: string): HTMLImageElement | null {
  if (!imageCache) {
    return null;
  }
  return imageCache.get(tileType) || null;
}

/**
 * Check if tile images are loaded
 */
export function areTileImagesLoaded(): boolean {
  return imageCache !== null;
}

/**
 * Clear the image cache (useful for testing or manual cache invalidation)
 */
export function clearTileImageCache(): void {
  imageCache = null;
  loadingPromise = null;
}
