import React, { useContext } from 'react';
import { useTranslation } from 'react-i18next';

import PlayerContext from '../../context/player/context';

import Grid from '@mui/material/Grid';
import Typography from '@mui/material/Typography';

const Display = () => {
  const { t } = useTranslation();
  const { state: { playerstatus } } = useContext(PlayerContext);

  const dontBreak = {
    whiteSpace: 'nowrap',
    width: '100%',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  };

  return (
    <Grid container>
      <Typography sx={dontBreak} component="h5" variant="h5">
        {playerstatus?.trackid
          ? (playerstatus?.title || t('player.display.unknown-title'))
          : t('player.display.no-song-in-queue')
        }
      </Typography>
      <Typography sx={dontBreak} variant="subtitle1" color="textSecondary">
        {playerstatus?.trackid && (playerstatus?.artist || t('player.display.unknown-artist')) }
        <span sx={{ marginLeft: '5px', marginRight: '5px' }}>&bull;</span>
        {playerstatus?.trackid && (playerstatus?.album || playerstatus?.file) }
      </Typography>
    </Grid>
  );
};

export default Display;
