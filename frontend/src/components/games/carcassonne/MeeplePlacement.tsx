'use client';

import { ValidAction } from '@/lib/types';

interface MeeplePlacementProps {
  validActions: ValidAction[];
  onMeeplePlaced: (spot: string) => void;
  onSkip: () => void;
  isMyTurn: boolean;
}

function formatSpotName(spot: string): string {
  const parts = spot.split('_');
  const featureType = parts[0];
  const directions = parts.slice(1).join('-');

  const featureNames: Record<string, string> = {
    'city': 'City',
    'road': 'Road',
    'field': 'Field',
    'monastery': 'Monastery',
  };

  const directionNames: Record<string, string> = {
    'N': 'North',
    'S': 'South',
    'E': 'East',
    'W': 'West',
    'NE': 'Northeast',
    'NW': 'Northwest',
    'SE': 'Southeast',
    'SW': 'Southwest',
    'EW': 'East-West',
    'NS': 'North-South',
  };

  const featureName = featureNames[featureType] || featureType;

  if (featureType === 'monastery') {
    return 'Monastery';
  }

  const directionName = directionNames[directions.toUpperCase()] || directions;
  return `${featureName} (${directionName})`;
}

export default function MeeplePlacement({
  validActions,
  onMeeplePlaced,
  onSkip,
  isMyTurn
}: MeeplePlacementProps) {
  const meepleSpots = validActions.filter(
    (action): action is { meeple_spot: string } => 'meeple_spot' in action
  );

  return (
    <div className="bg-white rounded-lg border shadow-sm">
      <div className="px-4 py-2 border-b font-semibold">Place Meeple</div>
      <div className="p-3 space-y-2">
        {meepleSpots.map((action, index) => {
          return (
            <button
              key={index}
              onClick={() => onMeeplePlaced(action.meeple_spot)}
              disabled={!isMyTurn}
              className="w-full px-3 py-2 text-sm font-medium rounded bg-blue-500 text-white hover:bg-blue-600 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
            >
              {formatSpotName(action.meeple_spot)}
            </button>
          );
        })}
        <button
          onClick={onSkip}
          disabled={!isMyTurn}
          className="w-full px-3 py-2 text-sm font-medium rounded bg-gray-200 text-gray-700 hover:bg-gray-300 disabled:bg-gray-100 disabled:cursor-not-allowed transition-colors"
        >
          Skip
        </button>
      </div>
    </div>
  );
}
