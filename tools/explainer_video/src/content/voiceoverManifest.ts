import raw from "../../public/vo/manifest.json";

/**
 * The synthesised voice track, produced by `scripts/make_voiceover.py`.
 *
 * The manifest always exists after `npm run assets`, but `clips` is empty when
 * no `FISH_API_KEY` was available, in which case the video renders with
 * captions and no narration.
 */
export type VoiceClip = {
  file: string;
  seconds: number;
  hash: string;
  words: number;
};

export type VoiceoverManifest = {
  generated: boolean;
  model?: string;
  reference_id?: string | null;
  reason?: string;
  clips: Record<string, VoiceClip>;
};

const manifest = raw as VoiceoverManifest;

export const HAS_VOICEOVER = Object.keys(manifest.clips).length > 0;

export const voiceClip = (sceneId: string): VoiceClip | undefined =>
  manifest.clips[sceneId];

export default manifest;
