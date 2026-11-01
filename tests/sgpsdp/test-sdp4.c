/* -*- Mode: C; tab-width: 4; indent-tabs-mode: t; c-basic-offset: 4 -*- */
/*
    Gpredict: Real-time satellite tracking and orbit prediction program

    Copyright (C)  2001-2008  Alexandru Csete.

    Comments, questions and bugreports should be submitted via
    http://sourceforge.net/projects/gpredict/
    More details can be found at the project home page:

            http://gpredict.oz9aec.net/
 
    This program is free software; you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation; either version 2 of the License, or
    (at your option) any later version.
  
    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.
  
    You should have received a copy of the GNU General Public License
    along with this program; if not, write to the
          Free Software Foundation, Inc.,
      59 Temple Place, Suite 330,
      Boston, MA  02111-1307
      USA
*/
/* Unit test for SGP4 */
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <math.h>
#include "sgp4sdp4.h"

#define TEST_STEPS 5

/* Directory holding the TLE file; set by tests/Makefile.am */
#ifndef TLE_DIR
#define TLE_DIR "."
#endif
#define TLE_FILE TLE_DIR "/test-sdp4.tle"

/* Accuracy check: largest accepted deviation from the Spacetrack Report #3
   values. Those come from a single-precision 1980 implementation, so a
   correct propagator can be some tens of metres off (the code in 2008 was
   off by up to 25 m, the current code by up to 9 m). */
#define STR3_POS_TOL 0.05       /* km */
#define STR3_VEL_TOL 5.0e-5     /* km/s */

/* Regression check: largest accepted deviation from the baseline below,
   loose enough for differences between CPUs and compilers. */
#define REG_POS_TOL 0.001       /* km */
#define REG_VEL_TOL 1.0e-6      /* km/s */

/* structure to hold a set of data */
typedef struct {
    double          t;
    double          x;
    double          y;
    double          z;
    double          vx;
    double          vy;
    double          vz;
} dataset_t;


const dataset_t expected[TEST_STEPS] = {
    {0.0,
     7473.37066650, 428.95261765, 5828.74786377,
     5.1071513, 6.44468284, -0.18613096},
    {360.0,
     -3305.22537232, 32410.86328125, -24697.17675781,
     -1.30113538, -1.15131518, -0.28333528},
    {720.0,
     14271.28759766, 24110.46411133, -4725.76837158,
     -0.32050445, 2.67984074, -2.08405289},
    {1080.0,
     -9990.05883789, 22717.35522461, -23616.890662501,
     -1.01667246, -2.29026759, 0.72892364},
    {1440.0,
     9787.86975097, 33753.34667969, -15030.81176758,
     -1.09425966, 0.92358845, -1.52230928}
};


/* Output of this code when the regression check was set up (2026-11-01),
   printed with eight decimals. Update it only after checking that a
   change in the results is intended. */
const dataset_t baseline[TEST_STEPS] = {
    {0.0,
     7473.37217894, 428.95457424, 5828.74790289,
     5.10715291, 6.44468284, -0.18613181},
    {360.0,
     -3305.22389961, 32410.86423224, -24697.17758780,
     -1.30113546, -1.15131509, -0.28333530},
    {720.0,
     14271.28739447, 24110.46241165, -4725.76687166,
     -0.32050430, 2.67984111, -2.08405302},
    {1080.0,
     -9990.05658196, 22717.36424399, -23616.89485741,
     -1.01667276, -2.29026675, 0.72892285},
    {1440.0,
     9787.87447948, 33753.34397245, -15030.80445210,
     -1.09425023, 0.92358992, -1.52230992}
};


char            tle_str[3][80];
sat_t           sat;


/* return 1 if the state in sat deviates from ref by more than the limits */
static int deviates(const sat_t * sat, const dataset_t * ref,
                    double pos_tol, double vel_tol)
{
    return fabs(sat->pos.x - ref->x) > pos_tol ||
        fabs(sat->pos.y - ref->y) > pos_tol ||
        fabs(sat->pos.z - ref->z) > pos_tol ||
        fabs(sat->vel.x - ref->vx) > vel_tol ||
        fabs(sat->vel.y - ref->vy) > vel_tol ||
        fabs(sat->vel.z - ref->vz) > vel_tol;
}

int main(void)
{
    FILE           *fp;
    int             i;
    int             failed = 0;

    /* read tle file */
    fp = fopen(TLE_FILE, "r");
    if (fp != NULL)
    {
        if (fgets(tle_str[0], 80, fp) == NULL)
        {
            printf("Error reading TLE line 1\n");
            fclose(fp);
            return 1;
        }
        if (fgets(tle_str[1], 80, fp) == NULL)
        {
            printf("Error reading TLE line 2\n");
            fclose(fp);
            return 1;
        }
        if (fgets(tle_str[2], 80, fp) == NULL)
        {
            printf("Error reading TLE line 3\n");
            fclose(fp);
            return 1;
        }
        fclose(fp);

        if (Get_Next_Tle_Set(tle_str, &sat.tle) == 1)
        {
            printf("TEST DATA:\n");
        }
        else
        {
            printf("Could not read TLE data 2\n");
            return 1;
        }
    }
    else
    {
        printf("Could not open %s\n", TLE_FILE);
        return 1;
    }

    printf("%s", tle_str[0]);
    printf("%s", tle_str[1]);
    printf("%s", tle_str[2]);

    select_ephemeris(&sat);

    printf("\nDEEP_SPACE_EPHEM: %d (expected %d)\n\n",
           (sat.flags & DEEP_SPACE_EPHEM_FLAG), DEEP_SPACE_EPHEM_FLAG);


    printf("                          RESULT            EXPECTED       "
           "     DELTA\n");
    printf("-----------------------------------------------------------"
           "----------------------\n");

    for (i = 0; i < TEST_STEPS; i++)
    {
        SDP4(&sat, expected[i].t);
        Convert_Sat_State(&sat.pos, &sat.vel);

        printf("STEP %d  t: %6.1f  X: %15.8f   %15.8f   %.8f (%.5f%%)\n",
               i + 1, expected[i].t, sat.pos.x, expected[i].x,
               fabs(sat.pos.x - expected[i].x),
               100.0 * fabs(sat.pos.x - expected[i].x) / fabs(expected[i].x));
        printf("                   Y: %15.8f   %15.8f   %.8f (%.5f%%)\n",
               sat.pos.y, expected[i].y,
               fabs(sat.pos.y - expected[i].y),
               100.0 * fabs(sat.pos.y - expected[i].y) / fabs(expected[i].y));
        printf("                   Z: %15.8f   %15.8f   %.8f (%.5f%%)\n",
               sat.pos.z, expected[i].z,
               fabs(sat.pos.z - expected[i].z),
               100.0 * fabs(sat.pos.z - expected[i].z) / fabs(expected[i].z));
        printf("                  VX: %15.8f   %15.8f   %.8f (%.5f%%)\n",
               sat.vel.x, expected[i].vx,
               fabs(sat.vel.x - expected[i].vx),
               100.0 * fabs(sat.vel.x -
                            expected[i].vx) / fabs(expected[i].vx));
        printf("                  VY: %15.8f   %15.8f   %.8f (%.5f%%)\n",
               sat.vel.y, expected[i].vy, fabs(sat.vel.y - expected[i].vy),
               100.0 * fabs(sat.vel.y -
                            expected[i].vy) / fabs(expected[i].vy));
        printf("                  VZ: %15.8f   %15.8f   %.8f (%.5f%%)\n",
               sat.vel.z, expected[i].vz, fabs(sat.vel.z - expected[i].vz),
               100.0 * fabs(sat.vel.z -
                            expected[i].vz) / fabs(expected[i].vz));

        if (deviates(&sat, &expected[i], STR3_POS_TOL, STR3_VEL_TOL))
        {
            printf("STEP %d  FAILED: deviation from Spacetrack Report #3 "
                   "above %.3f km or %.0e km/s\n",
                   i + 1, STR3_POS_TOL, STR3_VEL_TOL);
            failed = 1;
        }
        if (deviates(&sat, &baseline[i], REG_POS_TOL, REG_VEL_TOL))
        {
            printf("STEP %d  FAILED: deviation from baseline "
                   "above %.3f km or %.0e km/s\n",
                   i + 1, REG_POS_TOL, REG_VEL_TOL);
            failed = 1;
        }
    }

    return failed;
}
